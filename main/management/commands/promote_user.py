from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from main.models import UserProfile

class Command(BaseCommand):
    help = 'Promotes a user to an admin role and grants superuser status.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='The username of the user to promote.')

    def handle(self, *args, **kwargs):
        username = kwargs['username']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User with username "{username}" does not exist.'))
            return

        # Grant superuser and staff status
        user.is_superuser = True
        user.is_staff = True
        user.save()

        # Update or create the UserProfile with the admin role
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.role = 'admin'
        profile.is_verified = True # Admins should be verified by default
        profile.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f'Successfully created admin profile for "{username}".'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully updated "{username}" to be an admin.'))
