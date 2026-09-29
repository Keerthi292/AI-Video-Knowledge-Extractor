<script lang="ts">
	import { fly } from 'svelte/transition';
	import Confetti from '$lib/Confetti.svelte';
	import { motion } from '$lib/motion';

	/** Bump `trigger` to play the celebration once. */
	let { trigger, message }: { trigger: number; message: string } = $props();

	let visible = $state(false);

	$effect(() => {
		if (!trigger) return;
		visible = true;
		const timer = setTimeout(() => (visible = false), 3500);
		return () => clearTimeout(timer);
	});
</script>

{#if visible}
	{#key trigger}
		<Confetti />
	{/key}
	<div class="celebration-toast" role="status" transition:fly={motion({ y: 24, duration: 250 })}>
		{message}
	</div>
{/if}

<style>
	.celebration-toast {
		position: fixed;
		/* Centered without transform, which the fly transition animates. */
		left: 1rem;
		right: 1rem;
		margin: 0 auto;
		width: fit-content;
		bottom: 1.5rem;
		z-index: 51;
		box-sizing: border-box;
		padding: 0.75rem 1.25rem;
		border-radius: 999px;
		background: linear-gradient(90deg, #ff3e00, #b45cd6);
		color: white;
		font-weight: 600;
		font-size: 0.95rem;
		text-align: center;
		box-shadow: 0 8px 24px rgba(20, 20, 30, 0.2);
	}
</style>
