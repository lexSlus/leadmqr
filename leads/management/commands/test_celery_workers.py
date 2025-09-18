from django.core.management.base import BaseCommand
from leads.models import FoundPhone
from ai_calls.tasks import enqueue_ai_call
import uuid


class Command(BaseCommand):
    help = 'Test Celery workers with simulated data'

    def handle(self, *args, **options):
        self.stdout.write("🧪 Testing Celery Workers...")
        
        # Создаем тестовый FoundPhone
        test_lead_key = f"test_{uuid.uuid4().hex[:8]}"
        test_phone = "+15551234567"
        
        found_phone = FoundPhone.objects.create(
            lead_key=test_lead_key,
            phone=test_phone,
            variables={
                "customer_name": "Test Customer",
                "service_type": "Testing",
                "location": "Test City"
            }
        )
        
        self.stdout.write(f"✅ Created test FoundPhone: {found_phone.id}")
        self.stdout.write(f"   Lead Key: {test_lead_key}")
        self.stdout.write(f"   Phone: {test_phone}")
        
        # Отправляем задачу
        try:
            result = enqueue_ai_call.apply_async(
                args=[str(found_phone.id)], 
                queue="ai_calls"
            )
            self.stdout.write(f"✅ Task enqueued: {result.id}")
            self.stdout.write(f"   Queue: ai_calls")
            self.stdout.write(f"   Status: {result.status}")
            
        except Exception as e:
            self.stdout.write(f"❌ Failed to enqueue task: {e}")
            return
        
        self.stdout.write("\n💡 Check the following:")
        self.stdout.write("   1. Celery worker logs: docker compose logs -f celery_worker_ai")
        self.stdout.write("   2. Database for AICall: docker compose exec web python manage.py check_simulation_results")
        self.stdout.write("   3. Redis for task queue: docker compose exec redis redis-cli monitor")
        
        self.stdout.write(f"\n🔍 To check results:")
        self.stdout.write(f"   docker compose exec web python manage.py check_simulation_results --recent")
