"""Власні помилки модулів; `http` перекладає їх у відповіді однією обробкою."""


class NotSignedIn(Exception):
    """Немає чинної сесії: cookie відсутнє чи підроблене."""


class NotAllowed(Exception):
    """Акаунт не входить до дозволених (ALLOWED_EMAILS) або email не перевірено."""


class LoginExpired(Exception):
    """Сесія застаріла або Google більше не оновлює токен (тижневий тестовий вхід сплив)."""


class OAuthStateMismatch(Exception):
    """`state` у відповіді Google не збігається з cookie входу."""


class MissingScopes(Exception):
    """Мама надала не всі потрібні дозволи (Calendar, Tasks)."""

    def __init__(self, missing: frozenset[str]) -> None:
        super().__init__(f"missing scopes: {sorted(missing)}")
        self.missing = missing
