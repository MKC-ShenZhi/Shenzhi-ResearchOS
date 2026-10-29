import type {
  CcfRank,
  ConferenceDeadlineQuery,
  CoreRank,
  RankFilterValue,
  ThcplRank,
} from "../../../clients/backend/conferences";

export type RankSystem = "ccf" | "core" | "thcpl";

export type RankChip =
  | { system: "ccf"; value: RankFilterValue<CcfRank>; label: string }
  | { system: "core"; value: RankFilterValue<CoreRank>; label: string }
  | { system: "thcpl"; value: RankFilterValue<ThcplRank>; label: string };

/** Only ranks the ccf-deadlines data actually carries. */
export const RANK_CHIPS: readonly RankChip[] = [
  { system: "ccf", value: "A", label: "CCF-A" },
  { system: "ccf", value: "B", label: "CCF-B" },
  { system: "ccf", value: "C", label: "CCF-C" },
  { system: "core", value: "A*", label: "CORE-A*" },
  { system: "core", value: "A", label: "CORE-A" },
  { system: "core", value: "B", label: "CORE-B" },
  { system: "core", value: "C", label: "CORE-C" },
  { system: "thcpl", value: "A", label: "TH-CPL A" },
  { system: "thcpl", value: "B", label: "TH-CPL B" },
];

export interface ConferenceFilterState {
  categories: string[];
  ccf: RankFilterValue<CcfRank>[];
  core: RankFilterValue<CoreRank>[];
  thcpl: RankFilterValue<ThcplRank>[];
  /** Closed venues are hidden by default; most of a stale snapshot is closed. */
  includeClosed: boolean;
  q: string;
}

export const EMPTY_CONFERENCE_FILTERS: ConferenceFilterState = {
  categories: [],
  ccf: [],
  core: [],
  thcpl: [],
  includeClosed: false,
  q: "",
};

function toggle<T>(values: readonly T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

export function isRankChipActive(state: ConferenceFilterState, chip: RankChip): boolean {
  return (state[chip.system] as readonly string[]).includes(chip.value);
}

export function toggleRankChip(state: ConferenceFilterState, chip: RankChip): ConferenceFilterState {
  switch (chip.system) {
    case "ccf":
      return { ...state, ccf: toggle(state.ccf, chip.value) };
    case "core":
      return { ...state, core: toggle(state.core, chip.value) };
    case "thcpl":
      return { ...state, thcpl: toggle(state.thcpl, chip.value) };
  }
}

export function toggleCategory(state: ConferenceFilterState, category: string): ConferenceFilterState {
  return { ...state, categories: toggle(state.categories, category) };
}

export function hasActiveFilters(state: ConferenceFilterState): boolean {
  return (
    state.categories.length + state.ccf.length + state.core.length + state.thcpl.length > 0
    || state.q.trim() !== ""
  );
}

/** Rank chips are OR within one system and AND across systems (enforced by the backend). */
export function toDeadlineQuery(state: ConferenceFilterState): ConferenceDeadlineQuery {
  return {
    categories: state.categories,
    ccf: state.ccf,
    core: state.core,
    thcpl: state.thcpl,
    statuses: state.includeClosed ? [] : ["open", "tbd"],
    q: state.q.trim() || undefined,
  };
}
