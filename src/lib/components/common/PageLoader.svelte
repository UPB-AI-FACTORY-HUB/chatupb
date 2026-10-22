<script lang="ts">
	import { getContext } from 'svelte';
	import { fade } from 'svelte/transition';

	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n = getContext('i18n');

	export let className = '';
</script>

<!-- Full-area loading state, styled like the home page (same gradient, UPB swirl, brand dots) -->
<div
	class="relative flex h-full w-full items-center justify-center overflow-hidden bg-linear-to-b from-upb-50 via-white to-white dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 {className}"
	role="status"
	aria-live="polite"
	in:fade={{ duration: 150, delay: 150 }}
>
	<div class="flex flex-col items-center gap-5">
		<img
			src="{WEBUI_BASE_URL}/static/favicon.png"
			alt=""
			class="size-16 animate-[pulse_1.5s_cubic-bezier(0.4,0,0.6,1)_infinite]"
			draggable="false"
		/>

		<div class="flex items-center gap-1.5" aria-hidden="true">
			<span class="size-2 rounded-full bg-upb-blue animate-bounce [animation-delay:-0.3s]"></span>
			<span class="size-2 rounded-full bg-upb-gold animate-bounce [animation-delay:-0.15s]"></span>
			<span class="size-2 rounded-full bg-upb-navy animate-bounce dark:bg-white"></span>
		</div>

		<span class="sr-only">{$i18n.t('Loading...')}</span>
	</div>
</div>
