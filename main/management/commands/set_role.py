from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from main.models import UserProfile

User = get_user_model()

class Command(BaseCommand):
    help = 'Assigns a role to a user.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='The username of the user to update.')
        parser.add_argument('role', type=str, help='The role to assign (e.g., traveler, vendor, admin).')

    def handle(self, *args, **kwargs):
        username = kwargs['username']
        role = kwargs['role']

        if role not in [r[0] for r in UserProfile.ROLE_CHOICES]:
            raise CommandError(f'Invalid role "{role}". Must be one of: {[r[0] for r in UserProfile.ROLE_CHOICES]}')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist.')

        try:
            profile = user.userprofile
            profile.role = role
            profile.save()
            self.stdout.write(self.style.SUCCESS(f'Successfully updated role for "{username}" to "{role}".'))
        except UserProfile.DoesNotExist:
            # If the user exists but has no profile, create one
            UserProfile.objects.create(user=user, role=role)
            self.stdout.write(self.style.SUCCESS(f'Successfully created profile for "{username}" and set role to "{role}".'))
        except Exception as e:
            raise CommandError(f'An error occurred: {e}')
