class Media2TextError(Exception):
    code: str = "error"


class AuthRequired(Media2TextError):
    code = "auth_required"


class RateLimited(Media2TextError):
    code = "rate_limited"


class ParseFailed(Media2TextError):
    code = "parse_failed"


class PlatformChanged(Media2TextError):
    code = "platform_changed"


class RecordingError(Media2TextError):
    code = "recording_error"


class TranscribeError(Media2TextError):
    code = "transcribe_error"
