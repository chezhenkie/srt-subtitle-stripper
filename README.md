# strip_srt.py manual

Turns subtitle (.srt) or plain text files into clean text: removes cue numbers, timecodes and other non-letter lines, keeps every line with at least one letter, and guarantees a blank line between paragraphs. Made for reading long transcripts and for feeding them to AI agents.

## Run it

Needs Python 3, no packages. The input file is only read, never changed.

```
python strip_srt.py "video.srt"
```

Output lands next to the input as `video - alpha.txt`.

## Modes

```
python strip_srt.py "video.srt"                     text lines, blank lines kept
python strip_srt.py "video.srt" --keep-timecodes    [00:12:34] text, one line per cue
python strip_srt.py "video.srt" --numbered          00001 text
python strip_srt.py "video.srt" --numbered-only     00001 on its own line, text below
```

`--numbered` stacks on the timecode mode: `--keep-timecodes --numbered` gives `00001 [00:12:34] text`.

## Blank-line rule

Removing cue numbers and timecodes never glues two paragraphs together: if the removed lines were the only separator, a blank line is inserted there. Runs of blank lines collapse to one, trailing blanks are dropped.

## Examples

Input:
```
1
00:00:00,000 --> 00:00:04,040
I recently said with the start-up CDO for them of their product.

2
00:00:04,040 --> 00:00:08,240
His goal was to show me two remote systems alongside their application logs.
```

default:
```
I recently said with the start-up CDO for them of their product.

His goal was to show me two remote systems alongside their application logs.
```

--keep-timecodes --numbered:
```
00001 [00:00:00] I recently said with the start-up CDO for them of their product.

00002 [00:00:04] His goal was to show me two remote systems alongside their application logs.
```

--numbered-only:
```
00001
I recently said with the start-up CDO for them of their product.

00002
His goal was to show me two remote systems alongside their application logs.
```

## Naming and details

- Default names: `<name> - alpha.txt`, `<name> - timecodes.txt`, `<name> - numbered.txt`; stacked mode: `<name> - timecodes numbered.txt`. `--out "path"` sets your own.
- Counter runs 00001, 00002, ... up to 99999; beyond that it widens (100000) instead of wrapping.
- Multi-line cue text merges into one paragraph in timecode mode; same-cue lines stay together under one number in --numbered-only.
- Reads UTF-8 (BOM ok) or cp1252; writes UTF-8; keeps the file's original line endings.
- "Text" means a line with at least one letter (Unicode letters count); digit-only or symbol-only lines are treated as scaffolding and dropped.
