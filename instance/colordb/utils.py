
def split_abbreviations(s):
    abbreviations = []
    current_token = ''
    for char in s:
        if current_token is '':
            current_token += char
        elif char.islower():
            current_token += char
        else:
            abbreviations.append(str(current_token))
            current_token = ''
            current_token += char
    if current_token is not '':
        abbreviations.append(str(current_token))
    return abbreviations


def app_storage():
    from django.contrib.staticfiles.finders import AppStaticStorage
    return AppStaticStorage('colordb')