import redis
import json
import os
from functools import wraps
from datetime import timedelta
from typing import Any, Optional, Callable
from dotenv import load_dotenv

load_dotenv()

class RedisCache:
    """Redis cache class for data storage and management"""
    
    def __init__(self):
        # Cloud Redis connection using URL
        redis_url = os.getenv('REDIS_URL')
        if redis_url:
            print(f"Connecting to Redis Cloud...")
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=10,
                retry_on_timeout=True,
                health_check_interval=30
            )
        else:
            # Fallback to local Redis
            print("Connecting to local Redis...")
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                password=os.getenv('REDIS_PASSWORD'),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True
            )
        
        # Default cache TTL (Time-To-Live) in seconds
        self.default_ttl = int(os.getenv('REDIS_DEFAULT_TTL', 60))  # Reduced to 60s
        
        # Check connection
        try:
            self.redis_client.ping()
            print("Redis connection was successful")
        except Exception as e:
            print(f"Redis connection error: {e}")
            self.redis_client = None  # Failsafe
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache by key"""
        if not self.redis_client:
            return None
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except (redis.RedisError, json.JSONDecodeError):
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Write value to Redis cache with optional TTL"""
        if not self.redis_client:
            return False
        try:
            ttl = ttl or self.default_ttl
            # Convert object to JSON string
            serialized = json.dumps(value, default=str)
            return bool(self.redis_client.setex(key, ttl, serialized))
        except (redis.RedisError, TypeError):
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from Redis cache"""
        if not self.redis_client:
            return False
        try:
            return bool(self.redis_client.delete(key))
        except redis.RedisError:
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern (e.g. 'analytics*')"""
        if not self.redis_client:
            return 0
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                deleted = self.redis_client.delete(*keys)
                return deleted
            print(f"No keys found for pattern '{pattern}'")
            return 0
        except redis.RedisError as e:
            print(f"Redis error in clear_pattern: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.redis_client:
            return False
        try:
            return bool(self.redis_client.exists(key))
        except redis.RedisError:
            return False
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment counter in cache"""
        if not self.redis_client:
            return None
        try:
            return self.redis_client.incrby(key, amount)
        except redis.RedisError:
            return None

# Global cache object, imported by app.py
cache = RedisCache()

# Cache invalidation helpers - automatic cache management after data changes
class CacheInvalidator:
    """Class for cache invalidation after data updates"""
    
    @staticmethod
    def invalidate_order_related():
        """Delete analytics cache when new order is created"""
        cache.clear_pattern("analytics*")
        print("Cache invalidated: analytics (order created)")

# Rate limiting functionality
class RateLimiter:
    """Request rate limiting class"""
    
    def __init__(self, cache_instance: RedisCache):
        self.cache = cache_instance
    
    def is_allowed(self, identifier: str, limit: int, window: int) -> bool:
        """Check if request is allowed according to rate limit"""
        if not self.cache.redis_client:
            return True  # If no Redis - allow all requests
            
        key = f"rate_limit:{identifier}"
        current = self.cache.increment(key)
        
        if current == 1:
            # First request - set expiration time
            self.cache.redis_client.expire(key, window)
            return True
        
        return current <= limit
    
    def get_remaining(self, identifier: str, limit: int) -> int:
        """Return remaining requests count in current window"""
        key = f"rate_limit:{identifier}"
        current = self.cache.get(key) or 0
        return max(0, limit - int(current))