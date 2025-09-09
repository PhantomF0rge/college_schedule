from django.db import models

class SiteConfig(models.Model):
    maintenance_enabled = models.BooleanField(
        "Техработы включены (показывать уведомление/заглушку)", default=False
    )
    maintenance_hard = models.BooleanField(
        "Жёсткая заглушка 503 (блокировать контент)", default=False,
        help_text="Если включено, всем не-админам показывается страница техработ (503)."
    )
    message = models.CharField(
        "Сообщение для пользователей",
        max_length=255,
        blank=True,
        default="Идут технические работы. Сервис скоро вернётся."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки сайта"
        verbose_name_plural = "Настройки сайта"

    def __str__(self):
        return "Настройки сайта (единственная запись)"