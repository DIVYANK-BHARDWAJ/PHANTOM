import re
from typing import Tuple

class RequestIntentClassifier:
    """
    Classifies customer request text into:
    - DELETION_AUTHORIZED: true deletion request
    - NOT_APPLICABLE: request does not authorize deletion (e.g. data export only, marketing unsubscribe only, correction only, general access inquiry)
    """

    # Phrases clearly stating the user wants to KEEP or NOT delete their account/data
    NON_DELETION_PATTERNS = [
        r"not asking for deletion",
        r"not a request to erase",
        r"not requesting deletion",
        r"leave the account",
        r"leave my profile",
        r"keep the account",
        r"keep my account",
        r"do not close",
        r"don't close",
        r"do not delete",
        r"don't delete",
        r"without removing any of my records",
        r"marketing lists only",
        r"continue using the service",
        r"invoices for my records",
        r"information request,\s*not a request",
        r"portable format\.\s*please keep",
    ]

    # Deletion indicators across supported languages
    DELETION_ROOTS = [
        "delet", "eras", "clos", "remov", "purg", "destroy", "wipe", "gone",
        # French
        "suppr", "effac",
        # Spanish / Portuguese
        "elimin", "exclu", "borr", "quit", "cancela",
        # German
        "lösch", "loesch",
        # Japanese
        "削除", "消去", "消して",
        # Korean
        "삭제", "해지", "탈퇴", "지워",
        # Other
        "tombstone"
    ]

    @classmethod
    def is_deletion_authorized(cls, text: str) -> bool:
        if not text:
            return False
        
        lower_text = text.lower()

        # Check explicit non-deletion signals first
        for pat in cls.NON_DELETION_PATTERNS:
            if re.search(pat, lower_text):
                return False

        # Check if any deletion root is present
        for root in cls.DELETION_ROOTS:
            if root in lower_text:
                return True

        # Default fallback
        return False

    def classify(self, text: str) -> Tuple[bool, str]:
        is_auth = self.is_deletion_authorized(text)
        return is_auth, "DELETION_AUTHORIZED" if is_auth else "NOT_APPLICABLE"
