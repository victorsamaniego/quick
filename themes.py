"""Canonical preferences stored in the existing User.theme_color column."""
THEMES = {
    'gold-classic': 'QuickGo Gold Classic',
    'dark-gold': 'Dark Gold',
    'black-gold': 'Black / Gold Strong',
    'sand': 'Light Gold / Sand',
}


def normalize_theme(value):
    if value in THEMES:
        return value
    # Old preferences remain in the database until the user saves a new choice.
    return 'dark-gold' if value == 'oscuro' else 'gold-classic'
