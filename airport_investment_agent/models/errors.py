# the base class everything else inherits from (so calling code can catch "anything airport-related" in one place if it wants)
class AirportDataError(Exception):
    pass


# for when someone asks to compare fewer than 2 airports
class InvalidAirportSelectionError(AirportDataError):
    pass


# for an IATA code we don't have data for
class UnknownAirportError(AirportDataError):
    pass


# for when the BTS on-time-performance source needed for completion_rate
# can't be found, reached, or doesn't cover the requested airport.
# Deliberately distinct from UnknownAirportError, not overlapping with it:
# UnknownAirportError means the T-100 annual traffic source has no rows at
# all for the code; this means the *separate* monthly on-time-performance
# source doesn't cover it (e.g. too few flights that month to appear in the
# extract) -- a real, known airport can hit this without ever being an
# UnknownAirportError.
class CompletionDataUnavailableError(AirportDataError):
    pass


# for when a region is requested that we can't deliver data
class UnknownRegionError(AirportDataError):
    pass
