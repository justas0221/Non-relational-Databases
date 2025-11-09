from flask import Blueprint, jsonify, session
from datetime import datetime
from redis_cache import cache

debug = Blueprint('debug', __name__)

def init_debug():
    """Initialize debug routes"""

    @debug.get("/debug/redis")
    def debug_redis():
        """DEBUG: Show all Redis keys (login optional - shows cart info if logged in)"""
        try:
            # All Redis keys
            all_keys = cache.redis_client.keys("*") if cache.redis_client else []
            all_keys_str = [k.decode() if isinstance(k, bytes) else k for k in all_keys]
            
            # Keys su TTL info
            keys_with_ttl = {}
            for key in all_keys_str:
                ttl = cache.redis_client.ttl(key)  # -1 = no expire, -2 = not exists
                keys_with_ttl[key] = {
                    "ttl_seconds": ttl if (ttl is not None and ttl >= 0) else None,
                    "status": "persistent" if ttl == -1 else ("expired" if ttl == -2 else "temporary")
                }
            
            # Cache keys (analytics)
            analytics_keys = [k for k in all_keys_str if 'analytics' in k]
            cache_values = {}
            for key in analytics_keys:
                val = cache.get(key)
                ttl = cache.redis_client.ttl(key)
                if val:
                    cache_values[key] = {
                        "ttl_seconds": ttl if (ttl is not None and ttl >= 0) else None
                    }
            
            result = {
                "all_redis_keys": all_keys_str,
                "total_keys": len(all_keys_str),
                "keys_with_ttl": keys_with_ttl,
                "analytics_cache": cache_values
            }
            
            # Optional: if logged in, show cart info
            user_id = session.get('user_id')
            if user_id:
                cart_key = f"cart:{user_id}"
                cart_items = []
                cart_ttl = None
                if cache.redis_client and cache.redis_client.exists(cart_key):
                    # Redis Set - get all members
                    cart_members = cache.redis_client.smembers(cart_key)
                    cart_items = [
                        (m.decode() if isinstance(m, bytes) else m) 
                        for m in cart_members
                    ]
                    cart_ttl = cache.redis_client.ttl(cart_key)
                result.update({
                    "user_id": user_id,
                    "cart_key": cart_key,
                    "cart_items": cart_items,
                    "cart_item_count": len(cart_items),
                    "cart_ttl_seconds": cart_ttl if (cart_ttl is not None and cart_ttl >= 0) else None
                })
            
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return debug
