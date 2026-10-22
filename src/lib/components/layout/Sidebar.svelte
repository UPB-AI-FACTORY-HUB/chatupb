<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { v4 as uuidv4 } from 'uuid';

	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		user,
		chats,
		settings,
		chatId,
		tags,
		folders as _folders,
		showSidebar,
		showSearch,
		mobile,
		pinnedChats,
		temporaryChatEnabled,
		channels,
		socket,
		config,
		isApp,
		models,
		selectedFolder,
		WEBUI_NAME,
		sidebarWidth
	} from '$lib/stores';
	import {
		loadNextChatListPage,
		refreshChatList,
		registerFolderRefreshHandler,
		setAllChatsRead,
		setChatActive,
		setChatReadAt
	} from '$lib/stores/chatList';
	import { onMount, getContext, tick, onDestroy } from 'svelte';

	const i18n = getContext('i18n');

	$: canImportChats = $user?.role === 'admin' || ($user?.permissions?.chat?.import ?? true);

	import {
		getAllTags,
		toggleChatPinnedStatusById,
		getChatById,
		updateChatFolderIdById,
		importChats,
		deleteAllChats,
		getChatListBySearchText,
		markChatsRead
	} from '$lib/apis/chats';
	import {
		createNewFolder,
		getFolders,
		getSharedFolders,
		updateFolderParentIdById
	} from '$lib/apis/folders';
	import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';

	import UserMenu from './Sidebar/UserMenu.svelte';
	import ChatItem from './Sidebar/ChatItem.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Loader from '../common/Loader.svelte';
	import Folder from '../common/Folder.svelte';
	import SidebarSection from './Sidebar/Section.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import SharedFolderItem from './Sidebar/SharedFolderItem.svelte';
	import { getChannels, createNewChannel } from '$lib/apis/channels';
	import ChannelModal from './Sidebar/ChannelModal.svelte';
	import ChannelItem from './Sidebar/ChannelItem.svelte';
	import SearchModal from './SearchModal.svelte';
	import FolderModal from './Sidebar/Folders/FolderModal.svelte';
	import PinnedModelList from './Sidebar/PinnedModelList.svelte';
	import EditPencilIcon from './Sidebar/icons/EditPencil.svelte';
	import SearchIcon from './Sidebar/icons/Search.svelte';
	import Sidebar from '../icons/Sidebar.svelte';
	import { slide } from 'svelte/transition';
	import HotkeyHint from '../common/HotkeyHint.svelte';
	import Dropdown from '../common/Dropdown.svelte';
	import DropdownMenu from '../common/DropdownMenu.svelte';
	import CheckIcon from '../icons/Check.svelte';
	import MoreHorizontalIcon from './Sidebar/icons/MoreHorizontal.svelte';
	import ChevronDown from '../icons/ChevronDown.svelte';

	const BREAKPOINT = 768;

	let scrollTop = 0;

	let navElement;
	let shiftKey = false;

	let selectedChatId = null;

	// Keep the optimistic sidebar highlight in sync with the active chat. Leaving the
	// chat view (e.g. navigating to an admin page) clears chatId, and programmatic
	// navigation such as cloning moves chatId to a different chat — in both cases the
	// previously-selected item must not stay highlighted. The optimistic on-click
	// highlight is preserved because a click sets selectedChatId without changing
	// chatId, so this reactive only re-runs once chatId catches up to the same value.
	$: selectedChatId = $chatId || null;

	let showCreateChannel = false;

	// Pagination variables
	let chatListLoading = false;
	let chatListReady = false;
	let allChatsLoaded = false;

	let showCreateFolderModal = false;

	let pinnedModels = [];

	let showPinnedModels = false;
	let showChannels = false;
	let showFolders = false;
	let showSharedFolders = false;
	let showChatsMenu = false;

	let folders = {};
	let folderRegistry: Record<
		string,
		{
			setFolderItems?: () => unknown;
			upsertChat?: (chat: Record<string, unknown>) => unknown;
			setChatActive?: (chatId: string, active: boolean) => boolean;
			setChatReadAt?: (chatId: string, lastReadAt: number) => boolean;
			setAllChatsRead?: () => unknown;
		}
	> = {};

	let newFolderId = null;

	let sharedFolders: any[] = [];

	$: isHome = $page.url.pathname === '/' && !$chatId && !$selectedFolder;

	$: if ($selectedFolder) {
		initFolders();
	}

	const initFolders = async () => {
		if ($config?.features?.enable_folders === false) {
			return;
		}

		const folderList = await getFolders(localStorage.token).catch((error) => {
			return [];
		});
		_folders.set(folderList.sort((a, b) => b.updated_at - a.updated_at));

		folders = {};

		// First pass: Initialize all folder entries
		for (const folder of folderList) {
			// Ensure folder is added to folders with its data
			folders[folder.id] = { ...(folders[folder.id] || {}), ...folder };

			if (newFolderId && folder.id === newFolderId) {
				folders[folder.id].new = true;
				newFolderId = null;
			}
		}

		// Second pass: Tie child folders to their parents
		for (const folder of folderList) {
			if (folder.parent_id) {
				// Ensure the parent folder is initialized if it doesn't exist
				if (!folders[folder.parent_id]) {
					folders[folder.parent_id] = {}; // Create a placeholder if not already present
				}

				// Initialize childrenIds array if it doesn't exist and add the current folder id
				folders[folder.parent_id].childrenIds = folders[folder.parent_id].childrenIds
					? [...folders[folder.parent_id].childrenIds, folder.id]
					: [folder.id];

				// Sort the children by updated_at field
				folders[folder.parent_id].childrenIds.sort((a, b) => {
					return folders[b].updated_at - folders[a].updated_at;
				});
			}
		}

		// Merge shared folders into the same structure
		try {
			sharedFolders = await getSharedFolders(localStorage.token);
		} catch (e) {
			sharedFolders = [];
		}

		for (const sf of sharedFolders) {
			if (folders[sf.id]) continue; // Already owned by user
			folders[sf.id] = { ...sf, shared: true };
		}

		// Build parent-child relationships for shared folders
		for (const sf of sharedFolders) {
			if (folders[sf.id]?.shared && sf.parent_id && folders[sf.parent_id]) {
				folders[sf.parent_id].childrenIds = folders[sf.parent_id].childrenIds
					? [...new Set([...folders[sf.parent_id].childrenIds, sf.id])]
					: [sf.id];
			}
		}
	};

	const initSharedFolders = async () => {
		await initFolders();
	};

	const createFolder = async ({ name, data, parent_id }) => {
		name = name?.trim();
		if (!name) {
			toast.error($i18n.t('Folder name cannot be empty.'));
			return;
		}

		// Check for duplicate names in the same parent
		const siblings = Object.values(folders).filter((folder) => folder.parent_id === parent_id);
		if (siblings.find((folder) => folder.name.toLowerCase() === name.toLowerCase())) {
			// If a folder with the same name already exists, append a number to the name
			let i = 1;
			while (
				siblings.find((folder) => folder.name.toLowerCase() === `${name} ${i}`.toLowerCase())
			) {
				i++;
			}

			name = `${name} ${i}`;
		}

		// Add a dummy folder to the list to show the user that the folder is being created
		const tempId = uuidv4();
		folders = {
			...folders,
			[tempId]: {
				id: tempId,
				name: name,
				parent_id: parent_id,
				created_at: Date.now(),
				updated_at: Date.now()
			}
		};

		const res = await createNewFolder(localStorage.token, {
			name,
			data,
			parent_id
		}).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			// newFolderId = res.id;
			await initFolders();
			showFolders = true;
		}
	};

	const initChannels = async () => {
		// default (none), group, dm type
		const res = await getChannels(localStorage.token).catch((error) => {
			return null;
		});

		if (res) {
			await channels.set(
				res.sort(
					(a, b) =>
						['', null, 'group', 'dm'].indexOf(a.type) - ['', null, 'group', 'dm'].indexOf(b.type)
				)
			);
		}
	};

	const initChatList = async () => {
		// Reset pagination variables
		console.log('initChatList');
		allChatsLoaded = false;
		chatListReady = false;

		initFolders();
		initSharedFolders();
		await Promise.all([
			(async () => {
				console.log('Init tags');
				const _tags = await getAllTags(localStorage.token);
				tags.set(_tags);
			})(),
			(async () => {
				console.log('Init chat list');
				await refreshChatRows();
			})()
		]);
	};

	const refreshChatRows = async () => {
		const result = await refreshChatList(localStorage.token, { refreshPinned: true });
		if (result.accepted) {
			await initFolders();
			await Promise.all(Object.values(folderRegistry).map((folder) => folder?.setFolderItems?.()));
			allChatsLoaded = result.allLoaded;
			chatListReady = true;
		}
	};

	const loadMoreChats = async () => {
		chatListLoading = true;

		const result = await loadNextChatListPage(localStorage.token);
		allChatsLoaded = result.allLoaded;

		chatListLoading = false;
	};

	const applyFolderUnreadCounts = (folderUnreadCounts: Record<string, number>) => {
		folders = Object.fromEntries(
			Object.entries(folders).map(([id, folder]) => [
				id,
				id in folderUnreadCounts ? { ...folder, unread_count: folderUnreadCounts[id] } : folder
			])
		);
		_folders.update((folderList) =>
			folderList.map((folder) =>
				folder.id in folderUnreadCounts
					? { ...folder, unread_count: folderUnreadCounts[folder.id] }
					: folder
			)
		);
	};

	const applyChatReadState = (data) => {
		if (data?.folder_unread_counts) {
			applyFolderUnreadCounts(data.folder_unread_counts);
		}

		if (data?.chat_id && typeof data?.last_read_at === 'number') {
			setChatReadAt(data.chat_id, data.last_read_at);
			for (const folder of Object.values(folderRegistry)) {
				folder?.setChatReadAt?.(data.chat_id, data.last_read_at);
			}
		}
	};

	const markAllChatsReadHandler = async () => {
		const res = await markChatsRead(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
		if (!res) return;

		showChatsMenu = false;
		if (res.folder_unread_counts) {
			applyFolderUnreadCounts(res.folder_unread_counts);
		}
		setAllChatsRead();
		for (const folder of Object.values(folderRegistry)) {
			folder?.setAllChatsRead?.();
		}
	};

	const importChatHandler = async (items, pinned = false, folderId = null) => {
		if (!canImportChats) {
			toast.error($i18n.t('Access prohibited'));
			return;
		}

		console.log('importChatHandler', items, pinned, folderId);
		for (const item of items) {
			console.log(item);
			if (item.chat) {
				await importChats(localStorage.token, [
					{
						chat: item.chat,
						meta: item?.meta ?? {},
						pinned: pinned,
						folder_id: folderId,
						created_at: item?.created_at ?? null,
						updated_at: item?.updated_at ?? null
					}
				]);
			}
		}

		initChatList();
	};

	const inputFilesHandler = async (files) => {
		console.log(files);

		for (const file of files) {
			const reader = new FileReader();
			reader.onload = async (e) => {
				const content = e.target.result;

				try {
					const chatItems = JSON.parse(content);
					importChatHandler(chatItems);
				} catch {
					toast.error($i18n.t(`Invalid file format.`));
				}
			};

			reader.readAsText(file);
		}
	};

	const tagEventHandler = async (type, tagName, chatId) => {
		console.log(type, tagName, chatId);
		if (type === 'delete') {
			initChatList();
		} else if (type === 'add') {
			initChatList();
		}
	};

	let draggedOver = false;

	const onDragOver = (e) => {
		e.preventDefault();

		// Check if a file is being draggedOver.
		if (e.dataTransfer?.types?.includes('Files')) {
			draggedOver = true;
		} else {
			draggedOver = false;
		}
	};

	const onDragLeave = () => {
		draggedOver = false;
	};

	const onDrop = async (e) => {
		e.preventDefault();
		console.log(e); // Log the drop event

		// Perform file drop check and handle it accordingly
		if (e.dataTransfer?.files) {
			const inputFiles = Array.from(e.dataTransfer?.files);

			if (inputFiles && inputFiles.length > 0) {
				console.log(inputFiles); // Log the dropped files
				inputFilesHandler(inputFiles); // Handle the dropped files
			}
		}

		draggedOver = false; // Reset draggedOver status after drop
	};

	let touchstart;
	let touchend;

	function checkDirection() {
		const screenWidth = window.innerWidth;
		const swipeDistance = Math.abs(touchend.screenX - touchstart.screenX);
		if (touchstart.clientX < 40 && swipeDistance >= screenWidth / 8) {
			if (touchend.screenX < touchstart.screenX) {
				showSidebar.set(false);
			}
			if (touchend.screenX > touchstart.screenX) {
				showSidebar.set(true);
			}
		}
	}

	const onTouchStart = (e) => {
		touchstart = e.changedTouches[0];
		console.log(touchstart.clientX);
	};

	const onTouchEnd = (e) => {
		touchend = e.changedTouches[0];
		checkDirection();
	};

	const onKeyDown = (e) => {
		if (e.key === 'Shift') {
			shiftKey = true;
		}
	};

	const onKeyUp = (e) => {
		if (e.key === 'Shift') {
			shiftKey = false;
		}
	};

	const onFocus = () => {};

	const onBlur = () => {
		shiftKey = false;
		selectedChatId = null;
	};

	const MIN_WIDTH = 220;
	const MAX_WIDTH = 480;

	let isResizing = false;

	let startWidth = 0;
	let startClientX = 0;

	const resizeStartHandler = (e: MouseEvent) => {
		if ($mobile) return;
		isResizing = true;

		startClientX = e.clientX;
		startWidth = $sidebarWidth ?? 280;

		document.body.style.userSelect = 'none';
	};

	const resizeEndHandler = () => {
		if (!isResizing) return;
		isResizing = false;

		document.body.style.userSelect = '';
		localStorage.setItem('sidebarWidth', String($sidebarWidth));
	};

	const resizeSidebarHandler = (endClientX) => {
		const dx = endClientX - startClientX;
		const newSidebarWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + dx));

		sidebarWidth.set(newSidebarWidth);
		document.documentElement.style.setProperty('--sidebar-width', `${newSidebarWidth}px`);
	};

	onMount(async () => {
		try {
			const width = Number(localStorage.getItem('sidebarWidth'));
			if (!Number.isNaN(width) && width >= MIN_WIDTH && width <= MAX_WIDTH) {
				sidebarWidth.set(width);
			}
		} catch {}

		document.documentElement.style.setProperty('--sidebar-width', `${$sidebarWidth}px`);
		sidebarWidth.subscribe((w) => {
			document.documentElement.style.setProperty('--sidebar-width', `${w}px`);
		});

		showSidebar.set(!$mobile ? localStorage.sidebar === 'true' : false);

		const unsubscribers = [
			mobile.subscribe((value) => {
				if ($showSidebar && value) {
					showSidebar.set(false);
				}

				if ($showSidebar && !value) {
					const navElement = document.getElementsByTagName('nav')[0];
					if (navElement) {
						navElement.style['-webkit-app-region'] = 'drag';
					}
				}
			}),
			showSidebar.subscribe(async (value) => {
				localStorage.sidebar = value;

				// nav element is not available on the first render
				const navElement = document.getElementsByTagName('nav')[0];

				if (navElement) {
					if ($mobile) {
						if (!value) {
							navElement.style['-webkit-app-region'] = 'drag';
						} else {
							navElement.style['-webkit-app-region'] = 'no-drag';
						}
					} else {
						navElement.style['-webkit-app-region'] = 'drag';
					}
				}

				if (value) {
					// Only fetch channels if the feature is enabled and user has permission
					if (
						$config?.features?.enable_channels &&
						($user?.role === 'admin' || ($user?.permissions?.features?.channels ?? true))
					) {
						await initChannels();
					}
					await initChatList();
				}
			}),
			settings.subscribe((value) => {
				if (pinnedModels != value?.pinnedModels ?? []) {
					pinnedModels = value?.pinnedModels ?? [];
					showPinnedModels = pinnedModels.length > 0;
				}
			})
		];

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);

		window.addEventListener('touchstart', onTouchStart);
		window.addEventListener('touchend', onTouchEnd);

		window.addEventListener('focus', onFocus);
		window.addEventListener('blur', onBlur);

		const dropZone = document.getElementById('sidebar');
		if (dropZone) {
			dropZone.addEventListener('dragover', onDragOver);
			dropZone.addEventListener('drop', onDrop);
			dropZone.addEventListener('dragleave', onDragLeave);
		}

		const socketInstance = $socket;
		socketInstance?.on('events', chatActiveEventHandler);
		socketInstance?.on('connect', refreshChatRows);

		const unregisterFolderRefreshHandler = registerFolderRefreshHandler((folderId, chat) => {
			if (folderId) {
				if (chat) {
					return folderRegistry[folderId]?.upsertChat?.(chat);
				}

				return folderRegistry[folderId]?.setFolderItems?.();
			}

			return Promise.all(Object.values(folderRegistry).map((folder) => folder?.setFolderItems?.()));
		});

		return () => {
			unsubscribers.forEach((unsubscriber) => unsubscriber());

			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);

			window.removeEventListener('touchstart', onTouchStart);
			window.removeEventListener('touchend', onTouchEnd);

			window.removeEventListener('focus', onFocus);
			window.removeEventListener('blur', onBlur);

			if (dropZone) {
				dropZone.removeEventListener('dragover', onDragOver);
				dropZone.removeEventListener('drop', onDrop);
				dropZone.removeEventListener('dragleave', onDragLeave);
			}

			socketInstance?.off('events', chatActiveEventHandler);
			socketInstance?.off('connect', refreshChatRows);

			unregisterFolderRefreshHandler();
		};
	});

	// Handler for chat events (defined outside onMount for proper cleanup)
	const chatActiveEventHandler = async (event: {
		chat_id: string;
		message_id: string;
		data: {
			type: string;
			data: {
				active?: boolean;
				folder_id?: string | null;
				last_read_at?: number;
				folder_unread_counts?: Record<string, number>;
			};
		};
	}) => {
		if (event.data?.type === 'chat:active') {
			const eventData = event.data.data ?? {};
			const active = eventData.active ?? false;
			const found = setChatActive(event.chat_id, active);
			let foundInFolder = false;
			for (const folder of Object.values(folderRegistry)) {
				foundInFolder = folder?.setChatActive?.(event.chat_id, active) || foundInFolder;
			}
			if (!foundInFolder && active && eventData.folder_id) {
				await folderRegistry[eventData.folder_id]?.setFolderItems?.();
			}
			if (!found && active) {
				await refreshChatRows();
			}
		} else if (event.data?.type === 'chat:list') {
			const eventData = event.data.data ?? {};
			const folderUnreadCounts = eventData.folder_unread_counts;
			if (folderUnreadCounts) {
				applyFolderUnreadCounts(folderUnreadCounts);
			}

			if (typeof eventData.last_read_at === 'number') {
				setChatReadAt(event.chat_id, eventData.last_read_at);
				for (const folder of Object.values(folderRegistry)) {
					folder?.setChatReadAt?.(event.chat_id, eventData.last_read_at);
				}
				return;
			}

			await refreshChatRows();
			if (eventData.folder_id) {
				await folderRegistry[eventData.folder_id]?.setFolderItems?.();
			}
		}
	};

	const newChatHandler = async () => {
		selectedChatId = null;
		selectedFolder.set(null);

		if ($user?.role !== 'admin' && $user?.permissions?.chat?.temporary_enforced) {
			await temporaryChatEnabled.set(true);
		} else {
			await temporaryChatEnabled.set(false);
		}

		setTimeout(() => {
			if ($mobile) {
				showSidebar.set(false);
			}
		}, 0);
	};

	const isWindows = /Windows/i.test(navigator.userAgent);
</script>

<ChannelModal
	bind:show={showCreateChannel}
	onSubmit={async (payload: any) => {
		let { type, name, is_private, access_grants, group_ids, user_ids } = payload ?? {};
		name = name?.trim();

		if (type === 'dm') {
			if (!user_ids || user_ids.length === 0) {
				toast.error($i18n.t('Please select at least one user for Direct Message channel.'));
				return;
			}
		} else {
			if (!name) {
				toast.error($i18n.t('Channel name cannot be empty.'));
				return;
			}
		}

		const res = await createNewChannel(localStorage.token, {
			type: type,
			name: name,
			is_private: is_private,
			access_grants: access_grants,
			group_ids: group_ids,
			user_ids: user_ids
		}).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			$socket.emit('join-channels', { auth: { token: $user?.token } });
			await initChannels();
			showCreateChannel = false;
			showChannels = true;
			goto(`/channels/${res.id}`);
		}
	}}
/>

<FolderModal
	bind:show={showCreateFolderModal}
	onSubmit={async (folder) => {
		await createFolder(folder);
		showCreateFolderModal = false;
	}}
/>

<!-- svelte-ignore a11y-no-static-element-interactions -->

{#if $showSidebar}
	<div
		class=" {$isApp
			? ' ml-[4.5rem] md:ml-0'
			: ''} fixed md:hidden z-40 top-0 right-0 left-0 bottom-0 bg-black/60 w-full min-h-screen h-screen flex justify-center overflow-hidden overscroll-contain"
		on:mousedown={() => {
			showSidebar.set(!$showSidebar);
		}}
	/>
{/if}

<SearchModal
	bind:show={$showSearch}
	onClose={() => {
		if ($mobile) {
			showSidebar.set(false);
		}
	}}
/>

<button
	id="sidebar-new-chat-button"
	class="hidden"
	on:click={() => {
		goto('/');
		newChatHandler();
	}}
/>

<svelte:window
	on:mousemove={(e) => {
		if (!isResizing) return;
		resizeSidebarHandler(e.clientX);
	}}
	on:mouseup={() => {
		resizeEndHandler();
	}}
/>

{#if !$mobile && !$showSidebar}
	<div
		class=" w-[42px] shrink-0 py-1 px-1 flex flex-col justify-between text-gray-700 dark:text-gray-300 hover:bg-gray-50/30 dark:hover:bg-gray-800/30 h-full z-10 transition-all border-e-[0.5px] border-gray-50 dark:border-gray-850/30"
		id="sidebar"
		role="navigation"
		aria-label={$i18n.t('Chat history')}
	>
		<button
			class="flex flex-col flex-1 {isWindows ? 'cursor-pointer' : 'cursor-[e-resize]'}"
			on:click={async () => {
				showSidebar.set(!$showSidebar);
			}}
		>
			<div class="pb-1">
				<Tooltip
					content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
					placement="right"
				>
					<button
						class="flex size-8.5 items-center justify-center transition group {isWindows
							? 'cursor-pointer'
							: 'cursor-[e-resize]'}"
						aria-label={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
					>
						<div
							class=" self-center flex size-[30px] items-center justify-center rounded-lg transition group-hover:bg-gray-50 dark:group-hover:bg-gray-900"
						>
							<img
								src="{WEBUI_BASE_URL}/static/favicon.png"
								class="sidebar-new-chat-icon size-5 rounded-full group-hover:hidden"
								alt=""
							/>

							<Sidebar className="size-4 hidden group-hover:flex" />
						</div>
					</button>
				</Tooltip>
			</div>

			<div class="-gap-0.5">
				<div class="">
					<Tooltip content={$i18n.t('New Chat')} placement="right">
						<a
							class=" cursor-pointer flex size-8 items-center justify-center transition group"
							href="/"
							draggable="false"
							on:click={async (e) => {
								e.stopImmediatePropagation();
								e.preventDefault();

								goto('/');
								newChatHandler();
							}}
							aria-label={$i18n.t('New Chat')}
						>
							<div
								class=" self-center flex size-[30px] items-center justify-center rounded-lg transition group-hover:bg-gray-50 dark:group-hover:bg-gray-900"
							>
								<EditPencilIcon className="size-4" strokeWidth="1.5" />
							</div>
						</a>
					</Tooltip>
				</div>

				<div>
					<Tooltip content={$i18n.t('Search')} placement="right">
						<button
							class=" cursor-pointer flex size-8 items-center justify-center transition group"
							on:click={(e) => {
								e.stopImmediatePropagation();
								e.preventDefault();

								showSearch.set(true);
							}}
							draggable="false"
							aria-label={$i18n.t('Search')}
						>
							<div
								class=" self-center flex size-[30px] items-center justify-center rounded-lg transition group-hover:bg-gray-50 dark:group-hover:bg-gray-900"
							>
								<SearchIcon className="size-4" strokeWidth="1.5" />
							</div>
						</button>
					</Tooltip>
				</div>
			</div>
		</button>

		<div>
			<div>
				<div class=" flex justify-center items-center">
					{#if $user !== undefined && $user !== null}
						<UserMenu role={$user?.role}>
							<button
								type="button"
								class=" cursor-pointer flex size-8.5 items-center justify-center transition group"
								aria-label={$i18n.t('User menu')}
							>
								<div
									class="self-center relative flex size-[30px] items-center justify-center rounded-lg transition group-hover:bg-gray-50 dark:group-hover:bg-gray-900"
								>
									<img
										src={`${WEBUI_API_BASE_URL}/users/${$user?.id}/profile/image`}
										class="size-5.5 object-cover rounded-full"
										alt={$i18n.t('Open User Profile Menu')}
										aria-label={$i18n.t('Open User Profile Menu')}
									/>

									{#if $config?.features?.enable_user_status}
										<div class="absolute -bottom-0.5 -right-0.5">
											<span class="relative flex size-2.5">
												<span
													class="relative inline-flex size-2.5 rounded-full {true
														? 'bg-green-500'
														: 'bg-gray-300 dark:bg-gray-700'} border-2 border-white dark:border-gray-900"
												></span>
											</span>
										</div>
									{/if}
								</div>
							</button>
						</UserMenu>
					{/if}
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- {$i18n.t('New Folder')} -->
<!-- {$i18n.t('Pinned')} -->

{#if $showSidebar}
	<div
		bind:this={navElement}
		id="sidebar"
		role="navigation"
		aria-label={$i18n.t('Chat history')}
		class="h-screen max-h-[100dvh] min-h-screen select-none {$showSidebar
			? 'bg-white dark:bg-gray-950 z-50'
			: ' bg-transparent z-0 '} {$isApp
			? `ml-[4.5rem] md:ml-0 `
			: ' transition-all duration-300 '} shrink-0 text-gray-700 dark:text-gray-300 text-sm leading-5 fixed top-0 left-0 overflow-x-hidden
        "
		transition:slide={{ duration: 250, axis: 'x' }}
		data-state={$showSidebar}
	>
		<div
			class=" my-auto flex flex-col justify-between h-screen max-h-[100dvh] w-[var(--sidebar-width)] overflow-x-hidden scrollbar-hidden z-50 border-e border-gray-100 dark:border-gray-850/30 {$showSidebar
				? ''
				: 'invisible'}"
		>
			<div
				class="sidebar px-3 pt-4 pb-2 flex items-center justify-between gap-1 text-gray-600 dark:text-gray-400 sticky top-0 z-10 -mb-2"
			>
				<a
					href="/"
					class="flex flex-1 min-w-0 items-center gap-3 px-1 no-drag-region"
					draggable="false"
					on:click={newChatHandler}
					aria-label={$WEBUI_NAME}
				>
					<img
						src="{WEBUI_BASE_URL}/static/favicon.png"
						class="size-10 shrink-0"
						alt="UPB"
						draggable="false"
					/>
					<span
						class="min-w-0 whitespace-nowrap text-[13px] font-medium leading-[1.25] text-upb-navy dark:text-gray-200"
					>
						Universidad<br />Privada Boliviana
					</span>
				</a>
				<Tooltip
					content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
					placement="bottom"
				>
					<button
						class="flex size-8 shrink-0 justify-center items-center rounded-lg hover:bg-gray-100/70 dark:hover:bg-gray-900 transition {isWindows
							? 'cursor-pointer'
							: 'cursor-[w-resize]'}"
						on:click={() => {
							showSidebar.set(!$showSidebar);
						}}
						aria-label={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
					>
						<div class=" self-center">
							<Sidebar className="size-5" />
						</div>
					</button>
				</Tooltip>

				<div
					class="{scrollTop > 0
						? 'visible'
						: 'invisible'} sidebar-bg-gradient-to-b bg-linear-to-b from-white dark:from-gray-950 to-transparent from-50% pointer-events-none absolute inset-0 -z-10 -mb-6"
				></div>
			</div>

			<div
				class="relative flex flex-col flex-1 overflow-y-auto scrollbar-hidden pt-4 pb-2.5"
				on:scroll={(e) => {
					if (e.target.scrollTop === 0) {
						scrollTop = 0;
					} else {
						scrollTop = e.target.scrollTop;
					}
				}}
			>
				<div class="pb-2 space-y-0.5">
					<div class="px-3 flex justify-center text-gray-700 dark:text-gray-300">
						<a
							id="sidebar-new-chat-button"
							class="group grow flex items-center gap-3.5 rounded-xl px-3 py-2.5 transition outline-none {isHome
								? 'bg-upb-100/70 text-upb-navy dark:bg-white/[0.06] dark:text-white'
								: 'hover:bg-upb-50 dark:hover:bg-gray-900'}"
							href="/"
							draggable="false"
							on:click={newChatHandler}
							aria-label={$i18n.t('New Chat')}
						>
							<div class="self-center flex size-5 shrink-0 items-center justify-center">
								<EditPencilIcon className=" size-5" strokeWidth="1.5" />
							</div>

							<div class="flex flex-1 self-center translate-y-[0.5px]">
								<div class=" self-center text-[15px] leading-5">{$i18n.t('New Chat')}</div>
							</div>

							<HotkeyHint name="newChat" className=" group-hover:visible invisible" />
						</a>
					</div>

					<div class="px-3 flex justify-center text-gray-700 dark:text-gray-300">
						<button
							id="sidebar-search-button"
							class="group grow flex items-center gap-3.5 rounded-xl px-3 py-2.5 hover:bg-upb-50 dark:hover:bg-gray-900 transition outline-none"
							on:click={() => {
								showSearch.set(true);
							}}
							draggable="false"
							aria-label={$i18n.t('Search')}
						>
							<div class="self-center flex size-5 shrink-0 items-center justify-center">
								<SearchIcon strokeWidth="1.5" className="size-5" />
							</div>

							<div class="flex flex-1 self-center translate-y-[0.5px]">
								<div class=" self-center text-[15px] leading-5">{$i18n.t('Search')}</div>
							</div>
							<HotkeyHint name="search" className=" group-hover:visible invisible" />
						</button>
					</div>
				</div>

				{#if ($models ?? []).length > 0 && (($settings?.pinnedModels ?? []).length > 0 || $config?.default_pinned_models)}
					<SidebarSection
						id="sidebar-models"
						bind:open={showPinnedModels}
						className="mt-0.5"
						name={$i18n.t('Models')}
						dragAndDrop={false}
					>
						<PinnedModelList bind:selectedChatId {shiftKey} />
					</SidebarSection>
				{/if}

				{#if $config?.features?.enable_channels && ($user?.role === 'admin' || ($user?.permissions?.features?.channels ?? true))}
					<SidebarSection
						id="sidebar-channels"
						bind:open={showChannels}
						className="mt-0.5"
						name={$i18n.t('Channels')}
						dragAndDrop={false}
						onAdd={$user?.role === 'admin' || ($user?.permissions?.features?.channels ?? true)
							? async () => {
									await tick();

									setTimeout(() => {
										showCreateChannel = true;
									}, 0);
								}
							: null}
						onAddLabel={$i18n.t('Create Channel')}
					>
						{#each $channels as channel, channelIdx (`${channel?.id}`)}
							<ChannelItem
								{channel}
								onUpdate={async () => {
									await initChannels();
								}}
							/>

							{#if channelIdx < $channels.length - 1 && channel.type !== $channels[channelIdx + 1]?.type}<hr
									class=" border-gray-100/40 dark:border-gray-800/10 my-1.5 w-full"
								/>
							{/if}
						{/each}
					</SidebarSection>
				{/if}

				<SidebarSection
					id="sidebar-chats"
					className="mt-0.5"
					name={$i18n.t('Recent chats')}
					on:change={async (e) => {
						selectedFolder.set(null);
					}}
					on:import={(e) => {
						importChatHandler(e.detail);
					}}
					on:drop={async (e) => {
						const { type, id, item } = e.detail;

						if (type === 'chat') {
							let chat = await getChatById(localStorage.token, id).catch((error) => {
								return null;
							});
							if (!chat && item) {
								if (!canImportChats) {
									toast.error($i18n.t('Access prohibited'));
									return;
								}

								chat = await importChats(localStorage.token, [
									{
										chat: item.chat,
										meta: item?.meta ?? {},
										pinned: false,
										folder_id: null,
										created_at: item?.created_at ?? null,
										updated_at: item?.updated_at ?? null
									}
								]);
							}

							if (chat) {
								console.log(chat);
								if (chat.folder_id) {
									const res = await updateChatFolderIdById(localStorage.token, chat.id, null).catch(
										(error) => {
											toast.error(`${error}`);
											return null;
										}
									);

									folderRegistry[chat.folder_id]?.setFolderItems();
								}

								if (chat.pinned) {
									const res = await toggleChatPinnedStatusById(localStorage.token, chat.id);
								}

								initChatList();
							}
						} else if (type === 'folder') {
							if (folders[id].parent_id === null) {
								return;
							}

							const res = await updateFolderParentIdById(localStorage.token, id, null).catch(
								(error) => {
									toast.error(`${error}`);
									return null;
								}
							);

							if (res) {
								await initFolders();
							}
						}
					}}
				>
					<svelte:fragment slot="action">
						<Dropdown bind:show={showChatsMenu} align="end">
							<Tooltip content={$i18n.t('More')}>
								<button
									type="button"
									class="flex items-center justify-center w-7 h-7 rounded-lg text-gray-300 hover:text-gray-500 dark:text-gray-600 dark:hover:text-gray-400 transition-colors duration-100"
									aria-label={$i18n.t('More')}
									on:pointerup|stopPropagation
								>
									<MoreHorizontalIcon className="size-3.5" strokeWidth="2" />
								</button>
							</Tooltip>

							<div slot="content">
								<DropdownMenu className="min-w-[170px]">
									<button
										class="flex h-[1.6875rem] w-full items-center gap-2 rounded-xl px-2 text-[13px] select-none cursor-pointer hover:bg-gray-50/40 dark:hover:bg-gray-800/40"
										on:click={markAllChatsReadHandler}
									>
										<CheckIcon className="size-3.5" />
										<div class="flex items-center">{$i18n.t('Mark all as read')}</div>
									</button>
								</DropdownMenu>
							</div>
						</Dropdown>
					</svelte:fragment>

					{#if $pinnedChats.length > 0}
						<div class="mb-1">
							<div class="flex flex-col space-y-1 rounded-xl">
								<Folder
									id="sidebar-pinned-chats"
									buttonClassName=" text-gray-500"
									on:import={(e) => {
										importChatHandler(e.detail, true);
									}}
									on:drop={async (e) => {
										const { type, id, item } = e.detail;

										if (type === 'chat') {
											let chat = await getChatById(localStorage.token, id).catch((error) => {
												return null;
											});
											if (!chat && item) {
												if (!canImportChats) {
													toast.error($i18n.t('Access prohibited'));
													return;
												}

												chat = await importChats(localStorage.token, [
													{
														chat: item.chat,
														meta: item?.meta ?? {},
														pinned: false,
														folder_id: null,
														created_at: item?.created_at ?? null,
														updated_at: item?.updated_at ?? null
													}
												]);
											}

											if (chat) {
												console.log(chat);
												if (chat.folder_id) {
													const res = await updateChatFolderIdById(
														localStorage.token,
														chat.id,
														null
													).catch((error) => {
														toast.error(`${error}`);
														return null;
													});
												}

												if (!chat.pinned) {
													const res = await toggleChatPinnedStatusById(localStorage.token, chat.id);
												}

												initChatList();
											}
										}
									}}
									name={$i18n.t('Pinned')}
								>
									<div
										class="ml-3 pl-1 mt-[1px] flex flex-col overflow-y-auto scrollbar-hidden border-s border-gray-100 dark:border-gray-900 text-gray-700 dark:text-gray-300"
									>
										{#each $pinnedChats as chat, idx (`pinned-chat-${chat?.id ?? idx}`)}
											<ChatItem
												className=""
												id={chat.id}
												title={chat.title}
												createdAt={chat.created_at}
												updatedAt={chat.updated_at}
												lastReadAt={chat.last_read_at}
												active={chat.active ?? false}
												{shiftKey}
												selected={selectedChatId === chat.id}
												on:select={() => {
													selectedChatId = chat.id;
												}}
												on:unselect={() => {
													selectedChatId = null;
												}}
												on:change={async () => {
													initChatList();
												}}
												onReadStateChange={applyChatReadState}
												on:tag={(e) => {
													const { type, name } = e.detail;
													tagEventHandler(type, name, chat.id);
												}}
											/>
										{/each}
									</div>
								</Folder>
							</div>
						</div>
					{/if}

					<div class=" flex-1 flex flex-col overflow-y-auto scrollbar-hidden">
						<div class="pt-1 space-y-0.5">
							{#if $chats}
								{#each $chats as chat, idx (`chat-${chat?.id ?? idx}`)}
									<ChatItem
										className=""
										id={chat.id}
										title={chat.title}
										createdAt={chat.created_at}
										updatedAt={chat.updated_at}
										lastReadAt={chat.last_read_at}
										active={chat.active ?? false}
										{shiftKey}
										selected={selectedChatId === chat.id}
										on:select={() => {
											selectedChatId = chat.id;
										}}
										on:unselect={() => {
											selectedChatId = null;
										}}
										on:change={async () => {
											initChatList();
										}}
										onReadStateChange={applyChatReadState}
										on:tag={(e) => {
											const { type, name } = e.detail;
											tagEventHandler(type, name, chat.id);
										}}
									/>
								{/each}

								{#if chatListReady && !allChatsLoaded}
									<Loader
										on:visible={(e) => {
											if (!chatListLoading) {
												loadMoreChats();
											}
										}}
									>
										<div
											class="w-full flex justify-center py-1 text-xs animate-pulse items-center gap-2"
										>
											<Spinner className=" size-4" />
											<div class=" ">{$i18n.t('Loading...')}</div>
										</div>
									</Loader>
								{/if}
							{:else}
								<div
									class="w-full flex justify-center py-1 text-xs animate-pulse items-center gap-2"
								>
									<Spinner className=" size-4" />
									<div class=" ">{$i18n.t('Loading...')}</div>
								</div>
							{/if}
						</div>
					</div>
				</SidebarSection>
			</div>

			<div
				class="px-3 pt-2 pb-3 sticky bottom-0 z-10 sidebar border-t border-gray-100 dark:border-gray-850/50 bg-white dark:bg-gray-950"
			>
				<div
					class=" sidebar-bg-gradient-to-t bg-linear-to-t from-white dark:from-gray-950 to-transparent from-50% pointer-events-none absolute inset-0 -z-10 -mt-6"
				></div>
				<div class="flex flex-col">
					{#if $user !== undefined && $user !== null}
						<UserMenu role={$user?.role} className="w-[calc(var(--sidebar-width)-1.5rem)]">
							<button
								type="button"
								class="group flex items-center rounded-xl py-2 px-2 w-full hover:bg-upb-50 dark:hover:bg-gray-900 transition"
								aria-label={$i18n.t('User menu')}
							>
								<div class=" self-center mr-3 relative flex-shrink-0">
									<img
										src={`${WEBUI_API_BASE_URL}/users/${$user?.id}/profile/image`}
										class="size-9 object-cover rounded-full"
										alt={$i18n.t('Open User Profile Menu')}
										aria-label={$i18n.t('Open User Profile Menu')}
									/>

									{#if $config?.features?.enable_user_status}
										<div class="absolute -bottom-0.5 -right-0.5">
											<span class="relative flex size-2.5">
												<span
													class="relative inline-flex size-2.5 rounded-full {true
														? 'bg-green-500'
														: 'bg-gray-300 dark:bg-gray-700'} border-2 border-white dark:border-gray-900"
												></span>
											</span>
										</div>
									{/if}
								</div>
								<div
									class=" self-center text-[15px] font-medium truncate text-gray-800 dark:text-gray-100"
								>
									{$user?.name}
								</div>
								<ChevronDown
									className="size-4 ml-2 shrink-0 text-gray-500 transition group-hover:text-gray-700 dark:group-hover:text-gray-300"
									strokeWidth="2"
								/>
							</button>
						</UserMenu>
					{/if}
				</div>
			</div>
		</div>
	</div>

	{#if !$mobile}
		<div
			class="relative flex items-center justify-center group border-l border-gray-50 dark:border-gray-850/30 hover:border-gray-200 dark:hover:border-gray-800 transition z-20"
			id="sidebar-resizer"
			on:mousedown={resizeStartHandler}
			role="separator"
		>
			<div
				class=" absolute -left-1.5 -right-1.5 -top-0 -bottom-0 z-20 cursor-col-resize bg-transparent"
			/>
		</div>
	{/if}
{/if}
