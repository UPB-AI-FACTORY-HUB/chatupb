<script lang="ts">
	import { getContext } from 'svelte';
	import { fade } from 'svelte/transition';

	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n = getContext('i18n');

	export let message = '';
</script>

<main
	class="fixed inset-0 z-[9999] flex flex-col items-center justify-center gap-4 bg-gradient-to-b from-upb-50 to-white px-6 text-center dark:from-gray-900 dark:to-gray-950"
	in:fade={{ duration: 200 }}
>
	<div class="relative h-36 w-64">
		<img
			src="{WEBUI_BASE_URL}/static/mascot.png"
			alt=""
			class="absolute left-14 top-0 size-36 object-contain"
			draggable="false"
		/>

		<!-- gears -->
		<svg class="absolute left-[196px] top-0.5 size-14" viewBox="-32 -32 64 64" aria-hidden="true">
			<circle r="26" fill="none" stroke="#4a86ee" stroke-width="7" stroke-dasharray="7.5 6.7" />
			<circle r="21" fill="#4a86ee" />
			<circle r="8" fill="#e3ebfa" />
		</svg>
		<svg
			class="absolute left-[218px] top-14 size-9"
			viewBox="-32 -32 64 64"
			aria-hidden="true"
		>
			<circle r="26" fill="none" stroke="#1f4fc8" stroke-width="7" stroke-dasharray="7.5 6.7" />
			<circle r="21" fill="#1f4fc8" />
			<circle r="8" fill="#e3ebfa" />
		</svg>

		<!-- wrench -->
		<svg class="absolute bottom-1 left-3 h-20 w-10 -rotate-12" viewBox="-12 -90 24 96" aria-hidden="true">
			<rect x="-5" y="-62" width="10" height="64" rx="5" fill="#fdb813" />
			<circle cy="-66" r="14" fill="#fdb813" />
			<rect x="-5" y="-84" width="10" height="16" fill="#e3ebfa" />
		</svg>
	</div>

	<h1 class="text-3xl font-bold tracking-tight text-upb-navy dark:text-white">
		{$i18n.t('Under maintenance')}
	</h1>

	<p class="max-w-md text-base text-upb-navy/80 dark:text-gray-300">
		{message || $i18n.t("We're improving ChatUPB. We'll be back shortly.")}
	</p>

	<button
		class="mt-2 rounded-full bg-upb-blue px-6 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
		on:click={() => location.reload()}
	>
		{$i18n.t('Try again')}
	</button>
</main>

