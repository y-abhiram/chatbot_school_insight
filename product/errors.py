"""Actionable provider errors without exposing exception contents."""
def assistant_error(error):
    from product.sql_engine import UnsafeSQL
    if isinstance(error,UnsafeSQL):return str(error)
    name=type(error).__name__;message=str(error).lower()
    if 'ratelimit' in name.lower() or 'rate limit' in message or 'resource_exhausted' in message:
        return 'This AI provider has reached its usage limit. Select another configured provider/model, or try again when its quota resets.'
    if name in ('TimeoutError','APITimeoutError'):
        return 'The assistant took too long to respond. Try again or select another configured model.'
    if name in ('AuthenticationError','PermissionDeniedError'):
        return 'The selected AI model is unavailable with the configured credentials. Ask your administrator to check provider access.'
    return 'The assistant could not finish this request. Check the configured model or try a simpler question.'
