<script lang="ts">
	import { getContext, createEventDispatcher } from 'svelte';
	import { fade } from 'svelte/transition';

	const dispatch = createEventDispatcher();

	import { user, temporaryChatEnabled, selectedFolder, WEBUI_NAME } from '$lib/stores';
	import { refreshChatList } from '$lib/stores/chatList';
	import { WEBUI_BASE_URL, WEBUI_VERSION } from '$lib/constants';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte';
	import DocumentText from '$lib/components/icons/DocumentText.svelte';
	import AcademicCap from '$lib/components/icons/AcademicCap.svelte';
	import DocumentChartBar from '$lib/components/icons/DocumentChartBar.svelte';
	import Calendar from '$lib/components/icons/Calendar.svelte';
	import ArrowRight from '$lib/components/icons/ArrowRight.svelte';
	import MessageInput from './MessageInput.svelte';
	import FolderPlaceholder from './Placeholder/FolderPlaceholder.svelte';
	import FolderTitle from './Placeholder/FolderTitle.svelte';

	const i18n = getContext('i18n');

	export let createMessagePair: Function;
	export let stopResponse: Function;

	export let autoScroll = false;

	export let atSelectedModel: Model | undefined;
	export let selectedModels: [''];

	export let history;

	export let prompt = '';
	export let files = [];
	export let messageInput = null;

	export let selectedToolIds = [];
	export let selectedSkillIds = [];
	export let selectedFilterIds = [];
	export let pendingOAuthTools = [];

	export let showCommands = false;

	export let imageGenerationEnabled = false;
	export let codeInterpreterEnabled = false;
	export let webSearchEnabled = false;

	export let onUpload: Function = (e) => {};
	export let onSelect = (e) => {};
	export let onChange = (e) => {};
	export let onWebSearchToggle: Function = () => {};

	export let toolServers = [];

	export let dragged = false;

	// Starter cards on the home screen; clicking one sends its prompt like a suggestion.
	const CARDS = [
		{
			icon: DocumentText,
			title: 'Institutional information',
			description: 'Regulations, schedules, contacts and more.',
			prompt:
				'What institutional information can you help me with, like regulations, schedules and contacts?',
			className:
				'bg-blue-50/70 border-blue-100 hover:border-blue-200 dark:bg-blue-400/[0.04] dark:border-blue-400/10 dark:hover:border-blue-400/25',
			iconClassName: 'bg-blue-100 text-upb-blue dark:bg-blue-400/15 dark:text-blue-300'
		},
		{
			icon: AcademicCap,
			title: 'Academic inquiry',
			description: 'Scholarships, enrollment, results, statistics.',
			prompt:
				'I have an academic question about scholarships, enrollment or results. What can you tell me?',
			className:
				'bg-violet-50/70 border-violet-100 hover:border-violet-200 dark:bg-violet-400/[0.04] dark:border-violet-400/10 dark:hover:border-violet-400/25',
			iconClassName: 'bg-violet-100 text-violet-700 dark:bg-violet-400/15 dark:text-violet-300'
		},
		{
			icon: DocumentChartBar,
			title: 'Reports and files',
			description: 'Generate and download PDF and Excel.',
			prompt: 'What reports can you generate for me in PDF or Excel?',
			className:
				'bg-emerald-50/70 border-emerald-100 hover:border-emerald-200 dark:bg-emerald-400/[0.04] dark:border-emerald-400/10 dark:hover:border-emerald-400/25',
			iconClassName: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
		},
		{
			icon: Calendar,
			title: 'Academic guidance',
			description: 'Courses, study plans, procedures and processes.',
			prompt:
				'I need academic guidance about courses, study plans and procedures. Where do I start?',
			className:
				'bg-amber-50/70 border-amber-100 hover:border-amber-200 dark:bg-amber-400/[0.04] dark:border-amber-400/10 dark:hover:border-amber-400/25',
			iconClassName: 'bg-amber-100 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300'
		}
	];

	$: firstName = ($user?.name ?? '').trim().split(/\s+/)[0];

	// True when viewing a shared folder the current user doesn't own AND lacks write access
	$: folderReadOnly =
		$selectedFolder != null &&
		$selectedFolder.user_id !== $user?.id &&
		$selectedFolder.permission !== 'write';
</script>

<!-- Decorative background, pinned to the chat pane rather than the scrolling content -->
<div class="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
	<div
		class="absolute inset-0 bg-linear-to-b from-upb-50 via-white to-white dark:from-gray-900 dark:via-gray-900 dark:to-gray-900"
	></div>

	<div
		class="hidden @4xl:block absolute -top-56 -right-48 size-[36rem] rounded-full bg-linear-to-bl from-upb-200/80 via-upb-100/70 to-upb-50/0 dark:from-upb-blue/20 dark:via-upb-blue/5 dark:to-transparent"
	></div>
	<div
		class="hidden @4xl:block absolute -top-64 -right-56 size-[40rem] rounded-full border border-upb-gold/40 dark:border-upb-gold/20"
	></div>

	<svg
		class="absolute bottom-0 left-0 w-full h-40 text-upb-50 dark:text-white/[0.02]"
		viewBox="0 0 1440 160"
		preserveAspectRatio="none"
	>
		<path fill="currentColor" d="M0 96C240 40 480 24 720 56s480 88 720 40v64H0Z" />
	</svg>

	<div
		class="hidden @5xl:block absolute bottom-10 right-12 -rotate-12 text-upb-navy dark:text-gray-300"
	>
		<div
			class="text-[1.65rem] leading-tight"
			style="font-family: 'Snell Roundhand', 'Brush Script MT', cursive;"
		>
			{$i18n.t('Your future starts here')}
		</div>
		<svg class="w-40 h-3 ml-8 text-upb-gold" viewBox="0 0 160 12" fill="none">
			<path
				d="M2 9C50 2 110 1 158 6"
				stroke="currentColor"
				stroke-width="3"
				stroke-linecap="round"
			/>
		</svg>
	</div>
</div>

<div class="relative m-auto w-full max-w-[58rem] px-2 pt-20 pb-10">
	{#if $temporaryChatEnabled}
		<Tooltip
			content={$i18n.t("This chat won't appear in history and your messages will not be saved.")}
			className="w-full flex justify-center mb-2"
			placement="top"
		>
			<div class="flex items-center gap-1.5 text-gray-500 text-xs my-1 w-fit">
				<EyeSlash strokeWidth="2" className="size-3.5" />{$i18n.t('Temporary Chat')}
			</div>
		</Tooltip>
	{/if}

	{#if $selectedFolder}
		<div
			class="w-full flex flex-col justify-center items-center text-3xl text-gray-800 dark:text-gray-100"
		>
			<FolderTitle
				folder={$selectedFolder}
				readOnly={folderReadOnly}
				onUpdate={async (folder) => {
					await refreshChatList(localStorage.token);
				}}
				onDelete={async () => {
					await refreshChatList(localStorage.token);

					selectedFolder.set(null);
				}}
			/>
		</div>
	{:else}
		<div
			class="flex items-center justify-center gap-6 px-2.5 @3xl:gap-10"
			in:fade={{ duration: 150 }}
		>
			<img
				src="{WEBUI_BASE_URL}/static/mascot.png"
				alt=""
				class="hidden @2xl:block shrink-0 w-44 h-auto"
				draggable="false"
			/>

			<div class="text-left min-w-0">
				<h1
					class="text-[1.625rem] @2xl:text-[2rem] leading-tight font-bold tracking-tight text-upb-navy dark:text-white"
				>
					{firstName ? $i18n.t('Hello, {{name}}!', { name: firstName }) : $i18n.t('Hello!')}
				</h1>
				<p class="mt-1.5 text-lg @2xl:text-2xl font-semibold text-upb-navy/85 dark:text-gray-200">
					{$i18n.t("I'm UPB's university assistant.")}
				</p>
				<p
					class="mt-3 max-w-xl text-[15px] @2xl:text-base leading-relaxed text-gray-600 dark:text-gray-400"
				>
					{$i18n.t(
						'I can help you with institutional information, academic questions, resources, schedules, PDF and Excel reports, and much more.'
					)}
				</p>
			</div>
		</div>

		<div
			class="mt-10 px-2.5 grid grid-cols-2 @4xl:grid-cols-4 gap-3 @2xl:gap-4"
			in:fade={{ duration: 200, delay: 100 }}
		>
			{#each CARDS as card}
				<button
					type="button"
					class="group flex flex-col text-left rounded-2xl border p-4 @2xl:p-5 transition hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-12px_rgba(20,36,107,0.2)] {card.className}"
					on:click={() => onSelect({ type: 'prompt', data: $i18n.t(card.prompt) })}
				>
					<div class="flex size-11 items-center justify-center rounded-full {card.iconClassName}">
						<svelte:component this={card.icon} className="size-5.5" strokeWidth="1.6" />
					</div>
					<div class="mt-4 text-[15px] font-semibold leading-snug text-upb-navy dark:text-gray-100">
						{$i18n.t(card.title)}
					</div>
					<div class="mt-1.5 flex flex-1 justify-between gap-3">
						<div class="text-[13px] leading-snug text-gray-500 dark:text-gray-400">
							{$i18n.t(card.description)}
						</div>
						<ArrowRight
							className="self-end size-4 shrink-0 text-upb-navy/70 transition group-hover:translate-x-0.5 dark:text-gray-400"
							strokeWidth="2"
						/>
					</div>
				</button>
			{/each}
		</div>
	{/if}

	<div class="text-base font-normal w-full mt-8 {atSelectedModel ? 'mt-10' : ''}">
		{#if !($selectedFolder && folderReadOnly)}
			<MessageInput
				bind:this={messageInput}
				{history}
				bind:selectedModels
				bind:files
				bind:prompt
				bind:autoScroll
				bind:selectedToolIds
				bind:selectedSkillIds
				bind:selectedFilterIds
				bind:imageGenerationEnabled
				bind:codeInterpreterEnabled
				bind:webSearchEnabled
				bind:atSelectedModel
				bind:showCommands
				bind:dragged
				{pendingOAuthTools}
				{toolServers}
				{stopResponse}
				{createMessagePair}
				placeholder={$i18n.t('How can I help you today?')}
				{onChange}
				{onUpload}
				{onWebSearchToggle}
				on:chatVariables
				on:submit={(e) => {
					dispatch('submit', e.detail);
				}}
			/>
		{/if}
	</div>

	{#if $selectedFolder}
		<div class="mx-auto px-4 md:max-w-3xl md:px-6 min-h-62" in:fade={{ duration: 200, delay: 200 }}>
			<FolderPlaceholder folder={$selectedFolder} />
		</div>
	{:else}
		<div
			class="mt-6 flex items-center justify-center gap-4 text-xs text-gray-400 dark:text-gray-500"
		>
			<span class="h-px w-20 bg-gray-200 dark:bg-gray-800"></span>
			<span>{$WEBUI_NAME} · v{WEBUI_VERSION}</span>
			<span class="h-px w-20 bg-gray-200 dark:bg-gray-800"></span>
		</div>
	{/if}
</div>
