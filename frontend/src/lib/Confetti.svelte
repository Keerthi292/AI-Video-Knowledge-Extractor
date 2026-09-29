<script lang="ts">
	import { prefersReducedMotion } from '$lib/motion';

	const COLORS = ['#ff3e00', '#6b8afd', '#2e9e5b', '#b45cd6', '#e0a800'];

	const pieces = prefersReducedMotion()
		? []
		: Array.from({ length: 90 }, (_, i) => ({
				left: Math.random() * 100,
				delay: Math.random() * 0.6,
				duration: 2.2 + Math.random() * 1.4,
				color: COLORS[i % COLORS.length],
				drift: (Math.random() - 0.5) * 160,
				rotate: Math.random() * 720,
				size: 6 + Math.random() * 6
			}));
</script>

<div class="confetti" aria-hidden="true">
	{#each pieces as p}
		<span
			style:left="{p.left}%"
			style:background={p.color}
			style:width="{p.size}px"
			style:height="{p.size * 0.45}px"
			style:animation-delay="{p.delay}s"
			style:animation-duration="{p.duration}s"
			style:--drift="{p.drift}px"
			style:--rotate="{p.rotate}deg"
		></span>
	{/each}
</div>

<style>
	.confetti {
		position: fixed;
		inset: 0;
		pointer-events: none;
		overflow: hidden;
		z-index: 50;
	}

	span {
		position: absolute;
		top: -12px;
		border-radius: 2px;
		animation-name: fall;
		animation-timing-function: cubic-bezier(0.25, 0.6, 0.5, 1);
		animation-fill-mode: forwards;
	}

	@keyframes fall {
		to {
			transform: translate(var(--drift), 105vh) rotate(var(--rotate));
		}
	}
</style>
