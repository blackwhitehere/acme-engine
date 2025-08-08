try:
    from prefect import flow
except Exception:
    # Fallback to a no-op decorator when Prefect is not available (e.g., in Lambda)
    def flow(fn):
        return fn

@flow
def example_flow():
    """
    Example flow function that does nothing.
    """
    print("This is an example flow function.")