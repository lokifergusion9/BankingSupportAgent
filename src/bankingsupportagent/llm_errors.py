from groq import APIError, BadRequestError


def model_could_not_fill_form(error: Exception) -> bool:
    """True when the model was asked to fill in a structured form (a route, a ticket) but refused or failed.

    This happens on attack messages. A normal call reports it as a 400 error. While the answer is being
    streamed, the same failure arrives as a bare APIError. Rate limits, timeouts and outages are NOT this:
    they must stay errors, so the customer is told to try again instead of being sent to a human by mistake.
    """
    if isinstance(error, BadRequestError):
        return True
    return type(error) is APIError and "tool choice is required" in str(error).lower()
