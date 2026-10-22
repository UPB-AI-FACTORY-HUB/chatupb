<script lang="ts">
	import { createEventDispatcher, getContext, onMount, tick } from 'svelte';

	import { goto } from '$app/navigation';
	import { fade, slide } from 'svelte/transition';

	import { getUsage } from '$lib/apis';
	import { userSignOut } from '$lib/apis/auths';

	import { showSettings, mobile, showSidebar, user, config } from '$lib/stores';

	import { WEBUI_API_BASE_URL } from '$lib/constants';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import DropdownMenu from '$lib/components/common/DropdownMenu.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import HelpCircleIcon from './icons/HelpCircle.svelte';
	import LogOutIcon from './icons/LogOut.svelte';
	import MapIcon from './icons/Map.svelte';
	import Settings from '$lib/components/icons/Settings.svelte';
	import KeyIcon from './icons/Key.svelte';
	import UserIcon from './icons/User.svelte';

	const i18n = getContext('i18n');

	export let show = false;
	export let role = '';

	export let help = false;

	export let className = 'w-[240px]';
	export let align = 'end';

	export let showActiveUsers = true;

	const dispatch = createEventDispatcher();

	let usage = null;
	const getUsageInfo = async () => {
		const res = await getUsage(localStorage.token).catch((error) => {
			console.error('Error fetching usage info:', error);
		});

		if (res) {
			usage = res;
		} else {
			usage = null;
		}
	};

	const handleDropdownChange = (state) => {
		dispatch('change', state);

		// Fetch usage info when dropdown opens, if user has permission
		if (state && ($config?.features?.enable_public_active_users_count || role === 'admin')) {
			getUsageInfo();
		}
	};
</script>

<Dropdown bind:show onOpenChange={handleDropdownChange} {align}>
	<slot />

	<div slot="content">
		<DropdownMenu className="{className} font-sans text-xs">
			{#if $user}
				<div>
					<button
						class="flex h-[1.6875rem] items-center gap-2 rounded-xl px-2 text-xs w-full hover:bg-gray-50/40 dark:hover:bg-gray-800/40 transition cursor-pointer select-none text-left"
						type="button"
						on:click={async () => {
							show = false;
							await showSettings.set('account');

							if ($mobile) {
								await tick();
								showSidebar.set(false);
							}
						}}
					>
						<div class="self-center shrink-0 size-4.5 flex items-center justify-center">
							<img
								src={`${WEBUI_API_BASE_URL}/users/${$user.id}/profile/image`}
								alt=""
								class="size-4.5 rounded-full object-cover"
							/>
						</div>
						<div class="self-center min-w-0 flex-1 truncate">{$user.name}</div>

						{#if showActiveUsers && ($config?.features?.enable_public_active_users_count || role === 'admin') && usage?.user_count}
							<Tooltip
								content={usage?.model_ids && usage?.model_ids.length > 0
									? `${$i18n.t('Running')}: ${usage.model_ids.join(', ')} ✨`
									: $i18n.t('Active Users')}
							>
								<div
									class="ml-auto flex shrink-0 items-center justify-end gap-1 rounded-full px-1.5 py-0.5 text-[11px] leading-none text-gray-500 dark:text-gray-400"
									on:mouseenter={() => {
										if ($config?.features?.enable_public_active_users_count || role === 'admin') {
											getUsageInfo();
										}
									}}
								>
									<span class="size-1.5 rounded-full bg-green-500" />
									<span>{usage.user_count}</span>
								</div>
							</Tooltip>
						{/if}
					</button>
				</div>
			{/if}

			{#if help}
				<hr class="border-gray-50/30 dark:border-gray-800/30 my-0.5 mx-1 p-0" />

				<!-- {$i18n.t('Help')} -->

				{#if $user?.role === 'admin'}
					<a
						href="https://docs.openwebui.com"
						target="_blank"
						draggable="false"
						class="flex h-[1.6875rem] items-center gap-2 rounded-xl px-2 text-[13px] w-full hover:bg-gray-50/40 dark:hover:bg-gray-800/40 transition cursor-pointer select-none"
						id="chat-share-button"
						on:click={() => {
							show = false;
						}}
					>
						<div class="self-center">
							<HelpCircleIcon className="size-3.5" />
						</div>
						<div class=" self-center truncate">{$i18n.t('Documentation')}</div>
					</a>

					<!-- Releases -->
					<a
						href="https://github.com/open-webui/open-webui/releases"
						target="_blank"
						draggable="false"
						class="flex h-[1.6875rem] items-center gap-2 rounded-xl px-2 text-[13px] w-full hover:bg-gray-50/40 dark:hover:bg-gray-800/40 transition cursor-pointer select-none"
						id="chat-share-button"
						on:click={() => {
							show = false;
						}}
					>
						<div class="self-center">
							<MapIcon className="size-3.5" />
						</div>
						<div class=" self-center truncate">{$i18n.t('Releases')}</div>
					</a>
				{/if}

				<button
					class="flex h-[1.6875rem] items-center gap-2 rounded-xl px-2 text-[13px] w-full hover:bg-gray-50/40 dark:hover:bg-gray-800/40 transition cursor-pointer select-none"
					type="button"
					id="chat-share-button"
					on:click={async () => {
						show = false;
						showSettings.set('shortcuts');

						if ($mobile) {
							await tick();
							showSidebar.set(false);
						}
					}}
				>
					<div class="self-center">
						<KeyIcon className="size-3.5" />
					</div>
					<div class=" self-center truncate">{$i18n.t('Keyboard')}</div>
				</button>
			{/if}

			<hr class="border-gray-50/30 dark:border-gray-800/30 my-0.5 mx-1 p-0" />

			{#if role === 'admin'}
				<a
					href="/admin"
					draggable="false"
					class="flex h-[1.6875rem] items-center gap-2 rounded-xl px-2 text-[13px] w-full hover:bg-gray-50/40 dark:hover:bg-gray-800/40 transition cursor-pointer select-none"
					on:click={async (e) => {
						if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) {
							return;
						}
						e.preventDefault();
						show = false;
						goto('/admin');
						if ($mobile) {
							await tick();
							showSidebar.set(false);
						}
					}}
				>
					<div class="self-center">
						<UserIcon className="size-3.5" strokeWidth="1.5" />
					</div>
					<div class=" self-center truncate">{$i18n.t('Admin Panel')}</div>
				</a>
			{/if}

			<button
				class="flex h-[1.6875rem] items-center gap-2 rounded-xl px-2 text-[13px] w-full hover:bg-gray-50/40 dark:hover:bg-gray-800/40 transition cursor-pointer select-none"
				type="button"
				on:click={async () => {
					show = false;

					await showSettings.set(true);

					if ($mobile) {
						await tick();
						showSidebar.set(false);
					}
				}}
			>
				<div class="self-center">
					<Settings className="size-3.5" strokeWidth="1.5" />
				</div>
				<div class=" self-center truncate">{$i18n.t('Settings')}</div>
			</button>

			<button
				class="flex h-[1.6875rem] items-center gap-2 rounded-xl px-2 text-[13px] w-full hover:bg-gray-50/40 dark:hover:bg-gray-800/40 transition cursor-pointer select-none"
				type="button"
				on:click={async () => {
					const res = await userSignOut();
					user.set(null);
					localStorage.removeItem('token');

					location.href = res?.redirect_url ?? '/auth';
					show = false;
				}}
			>
				<div class="self-center">
					<LogOutIcon className="size-3.5" strokeWidth="1.5" />
				</div>
				<div class=" self-center truncate">{$i18n.t('Sign Out')}</div>
			</button>
		</DropdownMenu>
	</div>
</Dropdown>
