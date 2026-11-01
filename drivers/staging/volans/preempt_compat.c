/*
 * Preemption helper ABI for the prebuilt Volans WLAN object.
 *
 * Keep these helpers in the WLAN composite object. Other kernel code keeps
 * the normal inline paths selected when preemption debugging is disabled.
 */
#include <linux/compiler.h>
#include <linux/kprobes.h>
#include <linux/preempt.h>
#include <linux/smp.h>

#if !defined(CONFIG_DEBUG_PREEMPT) && !defined(CONFIG_PREEMPT_TRACER)
/* The public header uses macros in this configuration. */
#undef add_preempt_count
#undef sub_preempt_count

void __kprobes add_preempt_count(int val);
void __kprobes sub_preempt_count(int val);

void __kprobes add_preempt_count(int val)
{
	preempt_count() += val;
}

void __kprobes sub_preempt_count(int val)
{
	preempt_count() -= val;
}
#endif

#ifndef CONFIG_DEBUG_PREEMPT
notrace unsigned int debug_smp_processor_id(void);

notrace unsigned int debug_smp_processor_id(void)
{
	return raw_smp_processor_id();
}
#endif
