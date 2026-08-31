<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import favicon from '$lib/assets/favicon.svg';
	import { auth } from '$lib/auth.svelte';
	import { theme } from '$lib/theme.svelte';
	import '../app.css';

	let { children } = $props();

	let onHistoryPage = $derived(page.url.pathname === '/history');

	onMount(() => {
		theme.init();
		auth.checkStored();
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<main>
	<button
		class="theme-toggle"
		aria-label={theme.value === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
		onclick={() => theme.toggle()}
	>
		{theme.value === 'dark' ? '☀️' : '🌙'}
	</button>

	<h1>AI Video Knowledge Extractor</h1>
	<p class="tagline">Turn any video into a structured, interactive learning roadmap.</p>

	{#if !auth.checked}
		<p class="status">Loading…</p>
	{:else if !auth.token}
		<section class="card auth-card">
			<h2>{auth.view === 'login' ? 'Log in' : 'Create an account'}</h2>
			<form
				onsubmit={(e) => {
					e.preventDefault();
					auth.submit();
				}}
			>
				<input
					type="email"
					class="url-input"
					placeholder="Email"
					bind:value={auth.emailInput}
					autocomplete="email"
					required
				/>
				<input
					type="password"
					class="url-input"
					placeholder={auth.view === 'signup' ? 'Password (min 8 characters)' : 'Password'}
					bind:value={auth.passwordInput}
					autocomplete={auth.view === 'login' ? 'current-password' : 'new-password'}
					minlength="8"
					required
				/>
				<button type="submit" class="analyze-btn" disabled={auth.loading}>
					{auth.loading ? 'Please wait…' : auth.view === 'login' ? 'Log in' : 'Sign up'}
				</button>
			</form>
			{#if auth.error}
				<p class="error">{auth.error}</p>
			{/if}
			<p class="auth-switch">
				{auth.view === 'login' ? "Don't have an account?" : 'Already have an account?'}
				<button
					class="link-btn"
					onclick={() => {
						auth.view = auth.view === 'login' ? 'signup' : 'login';
						auth.error = null;
					}}
				>
					{auth.view === 'login' ? 'Sign up' : 'Log in'}
				</button>
			</p>
		</section>
	{:else}
		<div class="account-bar">
			<span class="account-email">{auth.email}</span>
			<div class="account-bar-actions">
				{#if onHistoryPage}
					<a class="ai-action-btn" href="/">Hide history</a>
				{:else}
					<a class="ai-action-btn" href="/history">History</a>
				{/if}
				<button class="ai-action-btn" onclick={() => auth.logout()}>Log out</button>
			</div>
		</div>

		{@render children()}
	{/if}
</main>
