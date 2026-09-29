<script lang="ts">
	import { fade } from 'svelte/transition';
	import Logo from '$lib/Logo.svelte';
	import { motion } from '$lib/motion';

	let { durationMs }: { durationMs: number } = $props();
</script>

<div class="splash" role="status" aria-label="Loading" out:fade={motion({ duration: 450 })}>
	<div class="splash-inner">
		<div class="splash-logo" aria-hidden="true">
			<Logo />
			<span class="splash-ring"></span>
		</div>

		<h1 class="splash-title">AI Video Knowledge Extractor</h1>
		<p class="splash-tagline">Turn any video into a structured, interactive learning roadmap.</p>

		<div class="splash-bar">
			<span style:animation-duration="{durationMs}ms"></span>
		</div>
	</div>
</div>

<style>
	.splash {
		position: fixed;
		inset: 0;
		z-index: 100;
		display: grid;
		place-items: center;
		padding: 16px;
		box-sizing: border-box;
		background:
			radial-gradient(circle at 20% 15%, color-mix(in srgb, #ff3e00 14%, transparent), transparent 45%),
			radial-gradient(circle at 85% 85%, color-mix(in srgb, #b45cd6 16%, transparent), transparent 45%),
			linear-gradient(180deg, var(--page-bg-start) 0%, var(--page-bg-end) 100%);
		color: var(--text-primary);
	}

	.splash-inner {
		width: 100%;
		max-width: 32rem;
		text-align: center;
	}

	.splash-logo {
		position: relative;
		width: clamp(6rem, 24vw, 8.5rem);
		aspect-ratio: 1;
		margin: 0 auto 1.5rem;
		animation: logo-in 0.6s cubic-bezier(0.2, 0.9, 0.3, 1.3) both;
	}

	.splash-logo :global(svg) {
		position: relative;
		z-index: 1;
		width: 100%;
		height: 100%;
		filter: drop-shadow(0 10px 24px color-mix(in srgb, #ff3e00 35%, transparent));
		animation: logo-float 2.4s ease-in-out 0.6s infinite;
	}

	.splash-ring {
		position: absolute;
		inset: 0;
		border-radius: 28%;
		border: 2px solid color-mix(in srgb, #ff3e00 45%, transparent);
		animation: ring-pulse 1.6s ease-out 0.4s infinite;
	}

	.splash-logo :global(.node) {
		opacity: 0;
		animation: node-in 0.3s ease-out forwards;
	}

	.splash-logo :global(.node-1) {
		animation-delay: 0.7s;
	}

	.splash-logo :global(.node-2) {
		animation-delay: 0.9s;
	}

	.splash-logo :global(.node-3) {
		animation-delay: 1.1s;
	}

	.splash-title {
		margin: 0;
		font-size: clamp(1.6rem, 6.5vw, 2.6rem);
		line-height: 1.2;
		background: linear-gradient(90deg, #ff3e00, #b45cd6);
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
		animation: rise-in 0.5s ease-out 0.25s both;
	}

	.splash-tagline {
		margin: 0.6rem auto 0;
		max-width: 26rem;
		font-size: clamp(1rem, 4vw, 1.2rem);
		line-height: 1.5;
		color: var(--text-secondary);
		animation: rise-in 0.5s ease-out 0.45s both;
	}

	.splash-bar {
		width: min(16rem, 70%);
		height: 0.35rem;
		margin: 1.75rem auto 0;
		border-radius: 999px;
		background: var(--surface-hover);
		overflow: hidden;
		animation: rise-in 0.5s ease-out 0.6s both;
	}

	.splash-bar span {
		display: block;
		height: 100%;
		width: 100%;
		border-radius: inherit;
		background: linear-gradient(90deg, #ff3e00, #b45cd6);
		transform-origin: left;
		animation-name: bar-fill;
		animation-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
		animation-fill-mode: both;
	}

	@keyframes logo-in {
		from {
			opacity: 0;
			transform: scale(0.6) rotate(-8deg);
		}
	}

	@keyframes logo-float {
		50% {
			transform: translateY(-6px);
		}
	}

	@keyframes ring-pulse {
		from {
			transform: scale(1);
			opacity: 0.9;
		}
		to {
			transform: scale(1.45);
			opacity: 0;
		}
	}

	@keyframes node-in {
		from {
			opacity: 0;
			transform: translateY(4px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}

	@keyframes rise-in {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
	}

	@keyframes bar-fill {
		from {
			transform: scaleX(0);
		}
		to {
			transform: scaleX(1);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.splash-logo,
		.splash-logo :global(svg),
		.splash-ring,
		.splash-logo :global(.node),
		.splash-title,
		.splash-tagline,
		.splash-bar {
			animation: none;
			opacity: 1;
		}

		.splash-ring {
			display: none;
		}
	}
</style>
