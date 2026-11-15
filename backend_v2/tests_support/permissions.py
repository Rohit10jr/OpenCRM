"""Row rules for unrouted test-only document fixtures."""


class OpenRows:
    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return None
