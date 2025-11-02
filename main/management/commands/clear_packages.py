from django.core.management.base import BaseCommand
from main.models import TravelPackage

class Command(BaseCommand):
    help = 'Deletes all TravelPackage objects from the database'

    def handle(self, *args, **kwargs):
        self.stdout.write('Deleting all TravelPackage objects...')
        count, _ = TravelPackage.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} travel packages.'))
