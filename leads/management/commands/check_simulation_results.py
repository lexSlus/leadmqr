from django.core.management.base import BaseCommand
from leads.models import FoundPhone, ProcessedLead
from ai_calls.models import AICall
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Check results of simulation and system status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recent',
            action='store_true',
            help='Show only recent results (last hour)'
        )

    def handle(self, *args, **options):
        recent_only = options['recent']
        
        if recent_only:
            cutoff_time = timezone.now() - timedelta(hours=1)
            self.stdout.write("📊 Recent Results (last hour):")
        else:
            cutoff_time = None
            self.stdout.write("📊 All Results:")

        # Общая статистика
        self.show_general_stats(cutoff_time)
        
        # Детали по моделям
        self.show_processed_leads(cutoff_time)
        self.show_found_phones(cutoff_time)
        self.show_ai_calls(cutoff_time)
        
        # Системный статус
        self.show_system_status()

    def show_general_stats(self, cutoff_time):
        """Показывает общую статистику"""
        
        query_kwargs = {}
        if cutoff_time:
            query_kwargs['created_at__gte'] = cutoff_time
        
        processed_count = ProcessedLead.objects.filter(**query_kwargs).count()
        phone_count = FoundPhone.objects.filter(**query_kwargs).count()
        call_count = AICall.objects.filter(**query_kwargs).count()
        
        self.stdout.write("\n" + "="*50)
        self.stdout.write("📈 STATISTICS")
        self.stdout.write("="*50)
        self.stdout.write(f"ProcessedLeads: {processed_count}")
        self.stdout.write(f"FoundPhones: {phone_count}")
        self.stdout.write(f"AICalls: {call_count}")

    def show_processed_leads(self, cutoff_time):
        """Показывает детали ProcessedLead"""
        
        query_kwargs = {}
        if cutoff_time:
            query_kwargs['created_at__gte'] = cutoff_time
            
        leads = ProcessedLead.objects.filter(**query_kwargs).order_by('-created_at')[:10]
        
        if leads.exists():
            self.stdout.write(f"\n📋 ProcessedLeads ({leads.count()}):")
            for lead in leads:
                self.stdout.write(f"   Key: {lead.key}")
                self.stdout.write(f"   Created: {lead.created_at}")
        else:
            self.stdout.write(f"\n📋 ProcessedLeads: No data")

    def show_found_phones(self, cutoff_time):
        """Показывает детали FoundPhone"""
        
        query_kwargs = {}
        if cutoff_time:
            query_kwargs['created_at__gte'] = cutoff_time
            
        phones = FoundPhone.objects.filter(**query_kwargs).order_by('-created_at')[:10]
        
        if phones.exists():
            self.stdout.write(f"\n📱 FoundPhones ({phones.count()}):")
            for phone in phones:
                self.stdout.write(f"   Lead: {phone.lead_key}")
                self.stdout.write(f"   Phone: {phone.phone}")
                self.stdout.write(f"   Variables: {phone.variables}")
                self.stdout.write(f"   Created: {phone.created_at}")
                self.stdout.write("   ---")
        else:
            self.stdout.write(f"\n📱 FoundPhones: No data")

    def show_ai_calls(self, cutoff_time):
        """Показывает детали AICall"""
        
        query_kwargs = {}
        if cutoff_time:
            query_kwargs['created_at__gte'] = cutoff_time
            
        calls = AICall.objects.filter(**query_kwargs).order_by('-created_at')[:10]
        
        if calls.exists():
            self.stdout.write(f"\n📞 AICalls ({calls.count()}):")
            
            # Статистика по статусам
            status_counts = {}
            for call in calls:
                status = call.status
                status_counts[status] = status_counts.get(status, 0) + 1
            
            self.stdout.write("   Status distribution:")
            for status, count in status_counts.items():
                self.stdout.write(f"     {status}: {count}")
            
            # Детали звонков
            self.stdout.write("   Details:")
            for call in calls:
                self.stdout.write(f"     Lead: {call.lead_key}")
                self.stdout.write(f"     Phone: {call.to_phone}")
                self.stdout.write(f"     Status: {call.status}")
                self.stdout.write(f"     Created: {call.created_at}")
                if call.provider_call_id:
                    self.stdout.write(f"     Provider ID: {call.provider_call_id}")
                self.stdout.write("     ---")
        else:
            self.stdout.write(f"\n📞 AICalls: No data")

    def show_system_status(self):
        """Показывает статус системы"""
        
        self.stdout.write(f"\n🔧 SYSTEM STATUS")
        self.stdout.write("="*50)
        
        # Проверяем есть ли активные задачи
        recent_calls = AICall.objects.filter(
            created_at__gte=timezone.now() - timedelta(minutes=5)
        )
        
        if recent_calls.exists():
            self.stdout.write("✅ System is active - recent AI calls found")
        else:
            self.stdout.write("⚠️  No recent activity")
        
        # Проверяем ошибки в звонках
        error_calls = AICall.objects.filter(status=AICall.Status.ERROR)
        if error_calls.exists():
            self.stdout.write(f"❌ {error_calls.count()} failed calls found")
        
        # Проверяем успешные звонки
        success_calls = AICall.objects.filter(status=AICall.Status.FINISHED)
        if success_calls.exists():
            self.stdout.write(f"✅ {success_calls.count()} successful calls")
