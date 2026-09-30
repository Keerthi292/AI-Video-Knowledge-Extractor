import type { TextSegment } from './types';

/** Split text into plain text, ```fenced``` code blocks and `inline` code. */
export function parseCodeSegments(text: string): TextSegment[] {
	const segments: TextSegment[] = [];
	const pushText = (content: string) => {
		const inline = /`([^`\n]+)`/g;
		let last = 0;
		let m: RegExpExecArray | null;
		while ((m = inline.exec(content)) !== null) {
			if (m.index > last) segments.push({ type: 'text', content: content.slice(last, m.index) });
			segments.push({ type: 'inline', content: m[1] });
			last = inline.lastIndex;
		}
		if (last < content.length) segments.push({ type: 'text', content: content.slice(last) });
	};
	const fence = /```[^\n`]*\n?([\s\S]*?)```/g;
	let lastIndex = 0;
	let match: RegExpExecArray | null;
	while ((match = fence.exec(text)) !== null) {
		if (match.index > lastIndex) {
			pushText(text.slice(lastIndex, match.index));
		}
		segments.push({ type: 'code', content: match[1].replace(/\n$/, '') });
		lastIndex = fence.lastIndex;
	}
	if (lastIndex < text.length) {
		pushText(text.slice(lastIndex));
	}
	return segments;
}
