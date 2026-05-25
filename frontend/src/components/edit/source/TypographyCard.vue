<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// Typography card — the *only* settings card the Style tab shows for
// .txt / .md sources, so it's flat (no accordion) and split into
// always-visible sections so the operator sees every text-printing
// knob the second they land on the tab. The earlier accordion shape
// kept everything hidden behind a "+", which made the modal look like
// it had no font controls at all.

interface TypographyDraft {
  font: string
  font_size_mm: number
  line_spacing: number
  alignment: 'left' | 'center' | 'right'
  stroke_width_mm: number
  margin_mm: number
  page_width_mm: number
  page_height_mm: number
  bold: boolean
  italic: boolean
  letter_spacing_mm: number
  hershey_text: boolean
}

// ``mode`` decides which slice of the form is relevant for the active
// source: ``typography`` (.txt / .md) drives every knob because the
// renderer lays text out from scratch; ``document`` (PDF / DOCX / HTML)
// only needs the font face + stroke width because per-span size and
// position come from the source document.
withDefaults(
  defineProps<{
    typo: TypographyDraft
    fonts: string[]
    mode?: 'typography' | 'document'
  }>(),
  { mode: 'typography' },
)

const { t } = useI18n()

// Hershey-name → friendly label. Operators don't recognise "futural"
// as "Sans" or "timesrb" as "Serif bold". The dropdown still keys on
// the raw name so the value the backend receives is unchanged.
const FONT_LABELS: Record<string, string> = {
  futural: 'Sans (futural)',
  futuram: 'Sans medium (futuram)',
  rowmans: 'Roman (rowmans)',
  rowmand: 'Roman duplex (rowmand)',
  rowmant: 'Roman triplex (rowmant)',
  timesr: 'Times Roman (timesr)',
  timesrb: 'Times Roman bold (timesrb)',
  timesi: 'Times italic (timesi)',
  timesib: 'Times italic bold (timesib)',
  timesg: 'Times Gothic (timesg)',
  scripts: 'Script (scripts)',
  scriptc: 'Script complex (scriptc)',
  cursive: 'Cursive',
  gothiceng: 'Gothic English',
  gothicger: 'Gothic German',
  gothicita: 'Gothic Italian',
  gothgbt: 'Gothic GBT',
  gothgrt: 'Gothic GRT',
  gothitt: 'Gothic IT',
  greek: 'Greek',
  greekc: 'Greek complex',
  greeks: 'Greek simplex',
  cyrillic: 'Cyrillic',
  cyrilc_1: 'Cyrillic 1',
  japanese: 'Japanese',
  mathlow: 'Math lower',
  mathupp: 'Math upper',
  symbolic: 'Symbols',
  astrology: 'Astrology',
  meteorology: 'Meteorology',
  music: 'Music',
  markers: 'Markers',
}

// Pen-plotter-friendly fonts come first so the operator finds them
// without scrolling. Specialty / symbol fonts drop to the bottom but
// stay listed in case the source contains glyphs from them.
const PREFERRED_ORDER = [
  'futural', 'futuram',
  'rowmans', 'rowmand', 'rowmant',
  'timesr', 'timesrb', 'timesi', 'timesib', 'timesg',
  'scripts', 'scriptc', 'cursive',
  'gothiceng', 'gothicger', 'gothicita', 'gothgbt', 'gothgrt', 'gothitt',
  'greek', 'greekc', 'greeks',
  'cyrillic', 'cyrilc_1', 'japanese',
  'mathlow', 'mathupp', 'symbolic',
  'astrology', 'meteorology', 'music', 'markers',
]

interface FontOption {
  value: string
  label: string
}

function labelFor(name: string): string {
  return FONT_LABELS[name] ?? name
}

function sortedFonts(fonts: string[]): FontOption[] {
  const known = new Set(fonts)
  const ordered: string[] = []
  for (const name of PREFERRED_ORDER) {
    if (known.has(name)) {
      ordered.push(name)
      known.delete(name)
    }
  }
  // Append anything we didn't list (future Hershey additions etc.) so
  // nothing gets silently hidden.
  for (const name of [...known].sort()) ordered.push(name)
  // ``/fonts`` may still be in flight when the modal first renders
  // (empty array) — surface a minimal pen-plotter font list as a
  // fallback so the dropdown isn't blank and the bound value stays
  // visible.
  if (ordered.length === 0) {
    return [
      { value: 'futural', label: labelFor('futural') },
      { value: 'rowmans', label: labelFor('rowmans') },
      { value: 'timesr', label: labelFor('timesr') },
    ]
  }
  return ordered.map((name) => ({ value: name, label: labelFor(name) }))
}
</script>

<template>
  <!-- Live preview lives in the left pane; this card is the form.
       Typography sources (.txt / .md) get the full layout grid — font,
       size, bold / italic, alignment, line spacing, stroke width,
       margins and page size — because the renderer lays out from
       scratch. Document sources (PDF / DOCX / HTML) only expose the
       Hershey toggle + face + stroke width because the document
       itself dictates per-span size and position; everything else
       gets ignored by the backend re-render path. -->
  <div class="space-y-3">
    <!-- =================== DOCUMENT MODE TOGGLE =================== -->
    <section
      v-if="mode === 'document'"
      class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2 text-xs"
    >
      <h3 class="text-[11px] font-semibold uppercase tracking-wide text-slate-300">
        {{ t('typography.docHeader') }}
      </h3>
      <label class="flex items-start gap-2 text-slate-300">
        <input
          v-model="typo.hershey_text"
          type="checkbox"
          class="mt-0.5 h-3.5 w-3.5 rounded border-slate-700 bg-slate-900 text-sky-500"
        />
        <span>
          <span class="font-medium">{{ t('typography.hersheyToggle') }}</span>
          <span class="block text-[10px] text-slate-500 leading-snug">
            {{ t('typography.hersheyToggleHint') }}
          </span>
        </span>
      </label>
    </section>

    <!-- =================== FONT =================== -->
    <section
      v-if="mode === 'typography' || typo.hershey_text"
      class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2.5 text-xs"
    >
      <header class="flex items-baseline justify-between">
        <h3 class="text-[11px] font-semibold uppercase tracking-wide text-slate-300">
          {{ t('typography.fontSection') }}
        </h3>
        <span class="text-[10px] text-slate-500">{{ t('typography.fontHint') }}</span>
      </header>

      <label class="block text-slate-400">
        {{ t('convert.font') }}
        <select
          v-model="typo.font"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        >
          <option
            v-for="opt in sortedFonts(fonts)"
            :key="opt.value"
            :value="opt.value"
          >{{ opt.label }}</option>
        </select>
      </label>

      <div v-if="mode === 'typography'" class="grid grid-cols-2 gap-2">
        <label class="block text-slate-400">
          {{ t('convert.fontSize') }}
          <input
            v-model.number="typo.font_size_mm"
            type="number"
            step="0.5"
            min="1"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
        <label class="block text-slate-400">
          {{ t('convert.letterSpacing') }}
          <input
            v-model.number="typo.letter_spacing_mm"
            type="number"
            step="0.1"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
      </div>

      <!-- Bold / Italic only matter when laying out from scratch.
           Document spans carry their own bold/italic flags that the
           backend reads from the source. -->
      <div v-if="mode === 'typography'" class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label class="flex items-center gap-1.5 text-slate-300">
          <input
            v-model="typo.bold"
            type="checkbox"
            class="h-3.5 w-3.5 rounded border-slate-700 bg-slate-900 text-sky-500"
          />
          <span class="font-bold">{{ t('convert.bold') }}</span>
        </label>
        <label class="flex items-center gap-1.5 text-slate-300">
          <input
            v-model="typo.italic"
            type="checkbox"
            class="h-3.5 w-3.5 rounded border-slate-700 bg-slate-900 text-sky-500"
          />
          <span class="italic">{{ t('convert.italic') }}</span>
        </label>
      </div>

      <!-- Stroke width applies in both modes (cosmetic SVG attribute
           plus the visual hint to the simulator). -->
      <label class="block text-slate-400">
        {{ t('convert.strokeWidth') }}
        <input
          v-model.number="typo.stroke_width_mm"
          type="number"
          step="0.1"
          min="0.05"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
      </label>
    </section>

    <!-- =================== LAYOUT (typography sources only) =================== -->
    <section
      v-if="mode === 'typography'"
      class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2 text-xs"
    >
      <h3 class="text-[11px] font-semibold uppercase tracking-wide text-slate-300">
        {{ t('typography.layoutSection') }}
      </h3>
      <div class="grid grid-cols-2 gap-2">
        <label class="block text-slate-400">
          {{ t('convert.alignment') }}
          <select
            v-model="typo.alignment"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          >
            <option value="left">{{ t('typography.alignLeft') }}</option>
            <option value="center">{{ t('typography.alignCenter') }}</option>
            <option value="right">{{ t('typography.alignRight') }}</option>
          </select>
        </label>
        <label class="block text-slate-400">
          {{ t('convert.lineSpacing') }}
          <input
            v-model.number="typo.line_spacing"
            type="number"
            step="0.1"
            min="0.5"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
      </div>
    </section>

    <!-- =================== PAGE (typography sources only) =================== -->
    <section
      v-if="mode === 'typography'"
      class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2 text-xs"
    >
      <h3 class="text-[11px] font-semibold uppercase tracking-wide text-slate-300">
        {{ t('typography.pageSection') }}
      </h3>
      <div class="grid grid-cols-2 gap-2">
        <label class="block text-slate-400">
          {{ t('convert.margin') }}
          <input
            v-model.number="typo.margin_mm"
            type="number"
            step="any"
            min="0"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
        <span class="self-end text-[10px] text-slate-500 leading-snug">
          {{ t('typography.pageHint') }}
        </span>
        <label class="block text-slate-400">
          {{ t('convert.pageWidth') }}
          <input
            v-model.number="typo.page_width_mm"
            type="number"
            step="any"
            min="1"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
        <label class="block text-slate-400">
          {{ t('convert.pageHeight') }}
          <input
            v-model.number="typo.page_height_mm"
            type="number"
            step="any"
            min="1"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
      </div>
    </section>
  </div>
</template>
