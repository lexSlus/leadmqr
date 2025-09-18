from django.core.management.base import BaseCommand
from leads.models import FoundPhone, ProcessedLead
from ai_calls.models import AICall
from leads.tasks import process_single_lead_task
import uuid
import random


class Command(BaseCommand):
    help = 'Simulate full lead processing flow without Thumbtack access'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=3,
            help='Number of leads to simulate (default: 3)'
        )

    def handle(self, *args, **options):
        count = options['count']
        
        self.stdout.write(f"🚀 Simulating {count} leads processing...")
        
        # Очищаем предыдущие данные
        FoundPhone.objects.all().delete()
        ProcessedLead.objects.all().delete()
        AICall.objects.all().delete()
        
        self.stdout.write("✅ Cleaned previous test data")
        
        for i in range(count):
            self.simulate_lead(i + 1)
        
        # Показываем результаты
        self.show_results()

    def simulate_lead(self, lead_number):
        """Симулирует обработку одного лида через leads task"""
        
        # Генерируем тестовые данные
        lead_key = str(uuid.uuid4())[:8]
        phone = f"+1{random.randint(2000000000, 9999999999)}"
        name = f"Test Lead {lead_number}"
        
        self.stdout.write(f"\n📋 Processing Lead {lead_number}:")
        self.stdout.write(f"   Lead Key: {lead_key}")
        self.stdout.write(f"   Phone: {phone}")
        self.stdout.write(f"   Name: {name}")
        
        # Создаем объект лида как будто его нашел LeadProducer
        lead_data = {
            "lead_key": lead_key,
            "href": f"https://www.thumbtack.com/pro-leads/{lead_key}",
            "phone": phone,  # Симулируем что телефон уже найден
            "variables": {
                "customer_name": name,
                "service_type": random.choice(["Cleaning", "Plumbing", "Electrical", "Landscaping"]),
                "location": random.choice(["New York", "Los Angeles", "Chicago", "Houston"]),
            }
        }
        
        # Отправляем в leads task - она сама создаст FoundPhone и вызовет AI звонок
        try:
            result = process_single_lead_task.apply_async(args=[lead_data], queue="lead_proc")
            self.stdout.write(f"   ✅ Enqueued lead processing task: {result.id}")
            self.stdout.write(f"   📞 AI call will be triggered automatically by leads task")
        except Exception as e:
            self.stdout.write(f"   ❌ Failed to enqueue lead task: {e}")
        
        # Ждем немного и проверяем результаты
        import time
        time.sleep(2)  # Даем время на обработку
        
        # Проверяем создался ли FoundPhone
        found_phones = FoundPhone.objects.filter(lead_key=lead_key)
        if found_phones.exists():
            phone_obj = found_phones.first()
            self.stdout.write(f"   ✅ Created FoundPhone: {phone_obj.phone}")
        else:
            self.stdout.write(f"   ⚠️  FoundPhone not created yet")
        
        # Проверяем создался ли AICall
        ai_calls = AICall.objects.filter(lead_key=lead_key)
        if ai_calls.exists():
            call = ai_calls.first()
            self.stdout.write(f"   ✅ Created AICall: {call.status}")
        else:
            self.stdout.write(f"   ⚠️  AICall not created yet")

    def show_results(self):
        """Показывает итоговые результаты"""
        
        self.stdout.write("\n" + "="*50)
        self.stdout.write("📊 SIMULATION RESULTS")
        self.stdout.write("="*50)
        
        # Статистика по моделям
        processed_count = ProcessedLead.objects.count()
        phone_count = FoundPhone.objects.count()
        call_count = AICall.objects.count()
        
        self.stdout.write(f"ProcessedLeads: {processed_count}")
        self.stdout.write(f"FoundPhones: {phone_count}")
        self.stdout.write(f"AICalls: {call_count}")
        
        # Детали по звонкам
        if call_count > 0:
            self.stdout.write("\n📞 AI Calls Details:")
            for call in AICall.objects.all()[:5]:  # Показываем первые 5
                self.stdout.write(f"   Lead: {call.lead_key}")
                self.stdout.write(f"   Phone: {call.to_phone}")
                self.stdout.write(f"   Status: {call.status}")
                self.stdout.write(f"   Created: {call.created_at}")
                self.stdout.write("   ---")
        
        # Детали по телефонам
        if phone_count > 0:
            self.stdout.write("\n📱 Found Phones Details:")
            for phone in FoundPhone.objects.all()[:5]:  # Показываем первые 5
                self.stdout.write(f"   Lead: {phone.lead_key}")
                self.stdout.write(f"   Phone: {phone.phone}")
                self.stdout.write(f"   Variables: {phone.variables}")
                self.stdout.write("   ---")
        
        self.stdout.write("\n✅ Simulation completed!")
        self.stdout.write("💡 Check Celery logs to see AI calls processing")
