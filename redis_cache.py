import redis
import json
import os
from functools import wraps
from datetime import timedelta
from typing import Any, Optional, Callable
from dotenv import load_dotenv

load_dotenv()

class RedisCache:
    """Redis cache klasė duomenų saugojimui ir valdymui"""
    
    def __init__(self):
        # Cloud Redis prisijungimas naudojant URL
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
            # Fallback į lokalų Redis
            print("Connecting to local Redis...")
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                password=os.getenv('REDIS_PASSWORD'),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True
            )
        
        # Numatytasis cache gyvavimo laikas (TTL) sekundėmis
        self.default_ttl = int(os.getenv('REDIS_DEFAULT_TTL', 60))  # Sumažinta iki 60s
        
        # Patikrinti prisijungimą
        try:
            self.redis_client.ping()
            print("Redis prisijungimas sėkmingas")
        except Exception as e:
            print(f"Redis prisijungimo klaida: {e}")
            self.redis_client = None  # Failsafe
    
    def get(self, key: str) -> Optional[Any]:
        """Gauna reikšmę iš Redis cache pagal raktą"""
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
        """Įrašo reikšmę į Redis cache su pasirinktiniu TTL"""
        if not self.redis_client:
            return False
        try:
            ttl = ttl or self.default_ttl
            # Konvertuojame objektą į JSON string'ą
            serialized = json.dumps(value, default=str)
            return bool(self.redis_client.setex(key, ttl, serialized))
        except (redis.RedisError, TypeError):
            return False
    
    def delete(self, key: str) -> bool:
        """Ištrina raktą iš Redis cache"""
        if not self.redis_client:
            return False
        try:
            return bool(self.redis_client.delete(key))
        except redis.RedisError:
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Ištrina visus raktus atitinkančius šabloną (pvz. 'users:*')"""
        if not self.redis_client:
            return 0
        try:
            keys = self.redis_client.keys(pattern)
            print(f"Pattern '{pattern}' found keys: {keys}")
            if keys:
                deleted = self.redis_client.delete(*keys)
                print(f"Deleted {deleted} keys")
                return deleted
            print(f"No keys found for pattern '{pattern}'")
            return 0
        except redis.RedisError as e:
            print(f"Redis error in clear_pattern: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Patikrina ar raktas egzistuoja cache'e"""
        if not self.redis_client:
            return False
        try:
            return bool(self.redis_client.exists(key))
        except redis.RedisError:
            return False
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Padidina skaitiklį cache'e (naudojama rate limiting)"""
        if not self.redis_client:
            return None
        try:
            return self.redis_client.incrby(key, amount)
        except redis.RedisError:
            return None
    
    def set_session(self, session_id: str, data: dict, ttl: int = 3600):
        """Išsaugo sesijos duomenis (1 val. TTL pagal nutylėjimą)"""
        return self.set(f"session:{session_id}", data, ttl)
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Gauna sesijos duomenis pagal session_id"""
        return self.get(f"session:{session_id}")
    
    def delete_session(self, session_id: str) -> bool:
        """Ištrina sesijos duomenis"""
        return self.delete(f"session:{session_id}")

# Globalus cache objektas, kurį importuos app.py
cache = RedisCache()

def cache_result(key_prefix: str, ttl: Optional[int] = None):
    """Decorator'ius funkcijų rezultatų cache'inimui - PATOBULINTA VERSIJA"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not cache.redis_client:
                return func(*args, **kwargs)
            
            try:
                # PAPRASTESNIS cache key - be timestamp bucketing!
                cache_parts = [key_prefix]
                
                # Funkcijos argumentai
                if args:
                    cache_parts.append(str(hash(str(args))))
                
                # Request parametrai (tik svarbūs)
                try:
                    from flask import request
                    if hasattr(request, 'args') and request.args:
                        # Bypass cache jei refresh arba nocache
                        if request.args.get('_refresh') or request.args.get('nocache'):
                            print(f"Cache bypass: {key_prefix}")
                            return func(*args, **kwargs)
                        
                        # Tik svarbūs parametrai į cache key
                        important_params = ['q', 'limit', 'eventId', 'page', 'filter']
                        filtered_args = {k: v for k, v in request.args.items() 
                                       if k in important_params}
                        
                        if filtered_args:
                            cache_parts.append(str(hash(tuple(sorted(filtered_args.items())))))
                            
                except (ImportError, RuntimeError):
                    pass
                
                # STABILESNĖ cache key - be laiko komponentų
                cache_key = ":".join(cache_parts)
                
                # Gauti iš cache
                cached_result = cache.get(cache_key)
                if cached_result is not None:
                    print(f"Cache HIT: {key_prefix}")
                    return cached_result
                
                # Vykdyti funkciją
                result = func(*args, **kwargs)
                
                # Įrašyti į cache
                if cache.set(cache_key, result, ttl):
                    print(f"Cache SAVE: {key_prefix} (TTL: {ttl or cache.default_ttl}s)")
                
                return result
                
            except Exception as e:
                print(f"Cache error in {key_prefix}: {e}")
                return func(*args, **kwargs)
                
        return wrapper
    return decorator

def invalidate_cache_pattern(pattern: str):
    """Helper funkcija cache trinimui pagal šabloną"""
    return cache.clear_pattern(pattern)

# Cache raktų generatoriai - centralizuotas raktų valdymas
class CacheKeys:
    """Statinė klasė cache raktų generavimui"""
    
    @staticmethod
    def analytics_top_events(limit: int) -> str:
        """Top įvykių analitikos cache raktas"""
        return f"analytics:top_events:{limit}"
    
    @staticmethod
    def analytics_availability() -> str:
        """Bilietų prieinamumo analitikos cache raktas"""
        return "analytics:availability"

# Cache trinimo helper'iai - automatinis cache valdymas po duomenų keitimo
class CacheInvalidator:
    """Klasė cache trinimui po duomenų atnaujinimo"""
    
    @staticmethod
    def invalidate_order_related():
        """Ištrina analytics cache kai sukuriamas naujas orderis"""
        cache.clear_pattern("analytics*")
        print("Cache invalidated: analytics (order created)")

# Rate limiting funkcionalumas - apsauga nuo per dažnų užklausų
class RateLimiter:
    """Užklausų dažnio ribojimo klasė"""
    
    def __init__(self, cache_instance: RedisCache):
        self.cache = cache_instance
    
    def is_allowed(self, identifier: str, limit: int, window: int) -> bool:
        """Patikrina ar užklausa leidžiama pagal rate limit"""
        if not self.cache.redis_client:
            return True  # Jei nėra Redis - leisti visas užklausas
            
        key = f"rate_limit:{identifier}"
        current = self.cache.increment(key)
        
        if current == 1:
            # Pirma užklausa - nustatome galiojimo laiką
            self.cache.redis_client.expire(key, window)
            return True
        
        return current <= limit
    
    def get_remaining(self, identifier: str, limit: int) -> int:
        """Grąžina likusių užklausų skaičių dabartiniame lange"""
        key = f"rate_limit:{identifier}"
        current = self.cache.get(key) or 0
        return max(0, limit - int(current))

# Inicializuojame rate limiter'į
rate_limiter = RateLimiter(cache)