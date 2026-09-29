try:
    from planning import optimize_visits
except ImportError:
    from .planning import optimize_visits

__all__ = ["optimize_visits"]
