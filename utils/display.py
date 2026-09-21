"""Small presentation helpers; never alter values stored in the database."""


def platform_label(value):
    return {'pc': 'ПК', 'mob': 'Мобильное устройство',
            'mobile': 'Мобильное устройство'}.get(value.lower(), value)
