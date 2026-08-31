<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/auth.svelte';
	import type { HistoryEntry } from '$lib/types';

	let historyItems: HistoryEntry[] | null = $state(null);
	let loading = $state(true);

	onMount(async () => {
		try {
			const response = await auth.fetch('/api/history');
			const data = await response.json();
			historyItems = (data.analyses as HistoryEntry[]) ?? [];
		} catch {
			historyItems = [];
		} finally {
			loading = false;
		}
	});
</script>

<a class="back-link" href="/">← Back to upload</a>

<section class="card history-card">
	<h2>Past Analyses</h2>
	{#if loading}
		<p class="ai-loading">Loading…</p>
	{:else if historyItems && historyItems.length === 0}
		<p class="roadmap-hint">No analyses yet — run one from the upload page.</p>
	{:else if historyItems}
		<ul class="history-list">
			{#each historyItems as item}
				<li>
					<a class="history-item" href="/analysis/{item.id}">
						<span class="history-source">{item.source}</span>
						<span class="history-intro">{item.intro}</span>
						{#if item.total_count > 0}
							<span class="history-progress-row">
								<span class="history-progress-bar">
									<span
										class="history-progress-fill"
										style:width="{(item.done_count / item.total_count) * 100}%"
									></span>
								</span>
								<span class="history-progress-label">
									{item.done_count} / {item.total_count} topics done
								</span>
							</span>
						{/if}
						<span class="history-date">{new Date(item.created_at).toLocaleString()}</span>
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</section>
