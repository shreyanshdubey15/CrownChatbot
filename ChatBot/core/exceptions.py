"""
Domain Exceptions — Entity-Centric Document Intelligence Platform
==================================================================
Typed exceptions for precise error handling across the pipeline.
"""


class DocIntelError(Exception):
    """Base exception for the Document Intelligence platform."""
    pass


class DocumentExtractionError(DocIntelError):
    """All extraction tiers failed for a document."""
    pass


class DocumentClassificationError(DocIntelError):
    """Document type could not be determined."""
    pass


class LayoutExtractionError(DocIntelError):
    """Layout model failed to extract spatial elements."""
    pass


class EntityResolutionError(DocIntelError):
    """Could not resolve or merge entity data."""
    pass


class ConfidenceBelowThreshold(DocIntelError):
    """Extracted value confidence is below the autofill threshold."""
    def __init__(self, field: str, confidence: float, threshold: float):
        self.field = field
        self.confidence = confidence
        self.threshold = threshold
        super().__init__(
            f"Field '{field}' confidence {confidence:.2f} < threshold {threshold:.2f}"
        )


class DualValidationConflict(DocIntelError):
    """LLM #1 and LLM #2 produced conflicting extractions."""
    def __init__(self, field: str, extractor_value: str, validator_value: str):
        self.field = field
        self.extractor_value = extractor_value
        self.validator_value = validator_value
        super().__init__(
            f"Validation conflict on '{field}': "
            f"extractor='{extractor_value}' vs validator='{validator_value}'"
        )


class GraphConnectionError(DocIntelError):
    """Neo4j or graph database connection failed."""
    pass


class VersionedMemoryError(DocIntelError):
    """Error in the versioned memory / event store."""
    pass


class AuditLogError(DocIntelError):
    """Failed to write audit trail entry."""
    pass


class RateLimitExceeded(DocIntelError):
    """API rate limit exceeded."""
    pass


class AuthenticationError(DocIntelError):
    """API key authentication failed."""
    pass






