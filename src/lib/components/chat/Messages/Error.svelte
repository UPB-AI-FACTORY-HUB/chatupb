<script lang="ts">
	import Info from '$lib/components/icons/Info.svelte';

	export let content: unknown = '';

	const getErrorMessage = (value: unknown): string => {
		if (typeof value === 'string') {
			return value;
		}

		if (typeof value === 'object' && value !== null) {
			const error = 'error' in value ? value.error : null;

			if (
				typeof error === 'object' &&
				error !== null &&
				'message' in error &&
				typeof error.message === 'string'
			) {
				return error.message;
			}

			if ('detail' in value && typeof value.detail === 'string') {
				return value.detail;
			}

			if ('message' in value && typeof value.message === 'string') {
				return value.message;
			}

			return JSON.stringify(value) ?? String(value);
		}

		return JSON.stringify(value) ?? String(value);
	};

	$: message = getErrorMessage(content) || 'Error submitting message';
</script>

<div
	class="my-1.5 flex w-full items-start gap-2.5 rounded-2xl border border-red-100 bg-red-50/70 px-4 py-2.5 text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300"
>
	<Info className="mt-0.5 size-4 shrink-0 text-red-400 dark:text-red-400" strokeWidth="1.8" />

	<div class="min-w-0 break-words text-[0.8125rem] leading-5">
		{message}
	</div>
</div>
