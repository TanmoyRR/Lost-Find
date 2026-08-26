import django.template.context

import pytest

original_base_copy = django.template.context.BaseContext.__copy__

def patched_base_copy(self):
    duplicate = object.__new__(type(self))
    duplicate.dicts = self.dicts[:]
    return duplicate

django.template.context.BaseContext.__copy__ = patched_base_copy


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup):
    """Ensure the pgvector extension exists when tests run on PostgreSQL."""
    from django.db import connection

    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
    return django_db_setup