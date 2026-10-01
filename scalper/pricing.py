"""Black-Scholes pricing used to mark simulated option positions."""
import math

MINUTES_PER_YEAR = 365 * 24 * 60


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(spot: float, strike: float, minutes_to_expiry: float, iv: float, right: str, r: float = 0.04) -> float:
    """Price of a call ('C') or put ('P'). Expiry is the 16:00 ET close."""
    intrinsic = max(spot - strike, 0.0) if right == "C" else max(strike - spot, 0.0)
    t = max(minutes_to_expiry, 0.0) / MINUTES_PER_YEAR
    if t <= 0 or iv <= 0:
        return intrinsic
    sd = iv * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / sd
    d2 = d1 - sd
    if right == "C":
        price = spot * _ncdf(d1) - strike * math.exp(-r * t) * _ncdf(d2)
    else:
        price = strike * math.exp(-r * t) * _ncdf(-d2) - spot * _ncdf(-d1)
    return max(price, intrinsic)
