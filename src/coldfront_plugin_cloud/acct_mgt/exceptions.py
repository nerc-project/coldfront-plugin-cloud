"""Defined exceptions used by acct-mgt."""


class ApiException(Exception):
    """Base exception class for errors.

    All exceptions subclassing ApiException will be caught from Flask's
    error handler and return the appropriate status code and message.
    The visible parameter controls whether the error message is visible
    to the end user.
    """

    status_code = 500
    visible = True
    default_message = "Internal Server Error."

    def __init__(self, message=None):
        self.message = message or self.default_message


class BadRequest(ApiException):
    """Exception class for invalid requests."""

    status_code = 400
    default_message = "Invalid Request."


class Conflict(BadRequest):
    """Exception class for requests that create already existing resources."""

    status_code = 409
    default_message = "Resource already exists."
