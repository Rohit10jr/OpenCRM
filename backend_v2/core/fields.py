"""Custom model fields shared by application models."""

from django.db import models

from core.secrets import encrypt


class EncryptedFieldMixin:
    """Encrypt before persistence and deliberately leave ciphertext on the instance."""

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        ciphertext = encrypt(value)
        setattr(model_instance, self.attname, ciphertext)
        return ciphertext


class EncryptedCharField(EncryptedFieldMixin, models.CharField):
    pass


class EncryptedTextField(EncryptedFieldMixin, models.TextField):
    pass
