import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from main.models import TravelPackage

class Command(BaseCommand):
    help = 'Seeds existing travel packages with images from Unsplash.'

    def get_placeholder_image(self):
        """Fetches a random image from picsum.photos."""
        try:
            url = 'https://picsum.photos/800/600'
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.content
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Error fetching placeholder image: {e}"))
        return None

    def handle(self, *args, **kwargs):
        self.stdout.write('Starting to seed package images...')

        packages_to_update = TravelPackage.objects.all()
        if not packages_to_update.exists():
            self.stdout.write(self.style.WARNING('No packages found. Exiting.'))
            return

        for i, package in enumerate(packages_to_update):
            self.stdout.write(f'Processing image for "{package.name}"...')

            image_content = self.get_placeholder_image()

            if image_content:
                try:
                    # Use a simple, unique filename
                    filename = f'package_{package.id}_{i}.jpg'
                    package.image.save(filename, ContentFile(image_content), save=True)
                    self.stdout.write(self.style.SUCCESS(f'  -> Successfully saved image for "{package.name}"'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  -> Failed to save image for "{package.name}": {e}'))
            else:
                self.stdout.write(self.style.WARNING(f'  -> Could not retrieve image for "{package.name}". Skipping.'))

        self.stdout.write(self.style.SUCCESS('Image seeding complete.'))
