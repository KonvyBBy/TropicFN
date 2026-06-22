import { useState } from "react";

interface FilterState {
  priceFrom: string;
  priceTo: string;
  searchTitle: string;
  accessEmail: boolean;
  changeableEmail: "no-matter" | "yes" | "no";
  xbLinked: "no-matter" | "maybe" | "no";
  psnLinked: "no-matter" | "maybe" | "no";
  outfitsFrom: string;
  outfitsTo: string;
  pickaxesFrom: string;
  pickaxesTo: string;
  dancesFrom: string;
  dancesTo: string;
  glidersFrom: string;
  glidersTo: string;
  vbucksFrom: string;
  vbucksTo: string;
}

const defaultFilters: FilterState = {
  priceFrom: "",
  priceTo: "",
  searchTitle: "",
  accessEmail: false,
  changeableEmail: "no-matter",
  xbLinked: "no-matter",
  psnLinked: "no-matter",
  outfitsFrom: "",
  outfitsTo: "",
  pickaxesFrom: "",
  pickaxesTo: "",
  dancesFrom: "",
  dancesTo: "",
  glidersFrom: "",
  glidersTo: "",
  vbucksFrom: "",
  vbucksTo: "",
};

type SectionKey =
  | "price"
  | "search"
  | "email"
  | "linkability"
  | "cosmetics-select"
  | "cosmetics"
  | "vbucks"
  | "stats"
  | "battlepass"
  | "other";

interface CollapsibleSectionProps {
  title: string;
  icon: string;
  sectionKey: SectionKey;
  openSections: Set<SectionKey>;
  onToggle: (key: SectionKey) => void;
  children?: React.ReactNode;
}

function CollapsibleSection({ title, icon, sectionKey, openSections, onToggle, children }: CollapsibleSectionProps) {
  const isOpen = openSections.has(sectionKey);
  return (
    <div className="rounded-xl overflow-hidden border border-border bg-secondary/30">
      <button
        className="w-full flex items-center justify-between px-3 py-2.5 cursor-pointer hover:bg-secondary/60 transition-colors"
        onClick={() => onToggle(sectionKey)}
      >
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 flex items-center justify-center">
            <i className={`${icon} text-primary text-xs`} />
          </div>
          <span className="text-xs font-bold text-foreground uppercase tracking-widest">{title}</span>
        </div>
        <i className={`${isOpen ? "ri-subtract-line" : "ri-add-line"} text-muted-foreground text-xs w-3 h-3 flex items-center justify-center`} />
      </button>
      {isOpen && children && (
        <div className="px-3 pb-3 space-y-2.5 border-t border-border/50 pt-2.5">
          {children}
        </div>
      )}
    </div>
  );
}

type TriStateVal = "no-matter" | "yes" | "no" | "maybe";
interface TriStateProps {
  label: string;
  value: TriStateVal;
  options: { label: string; value: TriStateVal }[];
  onChange: (val: TriStateVal) => void;
}

function TriState({ label, value, options, onChange }: TriStateProps) {
  return (
    <div className="space-y-1.5">
      <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{label}</span>
      <div className="flex gap-1 flex-wrap">
        {options.map((opt) => (
          <button
            key={opt.value}
            className={`px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wide transition-colors cursor-pointer whitespace-nowrap ${
              value === opt.value
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-secondary-foreground hover:bg-card-hover border border-border"
            }`}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

interface RangeInputProps {
  label: string;
  fromPlaceholder: string;
  toPlaceholder: string;
  fromVal: string;
  toVal: string;
  onFromChange: (v: string) => void;
  onToChange: (v: string) => void;
}

function RangeInput({ label, fromPlaceholder, toPlaceholder, fromVal, toVal, onFromChange, onToChange }: RangeInputProps) {
  return (
    <div className="space-y-1">
      {label && (
        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{label}</span>
      )}
      <div className="flex gap-1.5">
        <input
          type="number"
          placeholder={fromPlaceholder}
          value={fromVal}
          onChange={(e) => onFromChange(e.target.value)}
          className="w-full h-8 px-2 rounded-lg bg-secondary border border-border text-[11px] font-medium text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary/50"
        />
        <input
          type="number"
          placeholder={toPlaceholder}
          value={toVal}
          onChange={(e) => onToChange(e.target.value)}
          className="w-full h-8 px-2 rounded-lg bg-secondary border border-border text-[11px] font-medium text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary/50"
        />
      </div>
    </div>
  );
}

const triStateOpts = [
  { label: "Any", value: "no-matter" as TriStateVal },
  { label: "Yes", value: "yes" as TriStateVal },
  { label: "No", value: "no" as TriStateVal },
];

const triStateLinkOpts = [
  { label: "Any", value: "no-matter" as TriStateVal },
  { label: "Maybe", value: "maybe" as TriStateVal },
  { label: "No", value: "no" as TriStateVal },
];

export default function FilterPanel() {
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [openSections, setOpenSections] = useState<Set<SectionKey>>(
    new Set(["price", "search", "email", "linkability", "cosmetics", "vbucks"])
  );

  const toggleSection = (key: SectionKey) => {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const resetFilters = () => setFilters(defaultFilters);

  const update = <K extends keyof FilterState>(key: K, val: FilterState[K]) =>
    setFilters((prev) => ({ ...prev, [key]: val }));

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 flex items-center justify-center">
            <i className="ri-equalizer-2-fill text-primary text-sm" />
          </div>
          <h2 className="text-sm font-bold text-foreground uppercase tracking-widest">Filters</h2>
        </div>
        <button
          className="text-[10px] font-bold text-primary hover:text-primary/70 transition-colors cursor-pointer whitespace-nowrap uppercase tracking-wider border border-primary/30 px-2 py-1 rounded-lg hover:bg-primary/10"
          onClick={resetFilters}
        >
          Reset All
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-2">
        <CollapsibleSection title="Price" icon="ri-price-tag-3-line" sectionKey="price" openSections={openSections} onToggle={toggleSection}>
          <RangeInput
            label=""
            fromPlaceholder="Min €"
            toPlaceholder="Max €"
            fromVal={filters.priceFrom}
            toVal={filters.priceTo}
            onFromChange={(v) => update("priceFrom", v)}
            onToChange={(v) => update("priceTo", v)}
          />
        </CollapsibleSection>

        <CollapsibleSection title="Search" icon="ri-search-2-line" sectionKey="search" openSections={openSections} onToggle={toggleSection}>
          <input
            placeholder="Search by title..."
            value={filters.searchTitle}
            onChange={(e) => update("searchTitle", e.target.value)}
            className="w-full h-8 px-2.5 rounded-lg bg-secondary border border-border text-[11px] font-medium text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </CollapsibleSection>

        <CollapsibleSection title="Email" icon="ri-mail-check-line" sectionKey="email" openSections={openSections} onToggle={toggleSection}>
          <label className="flex items-center gap-2 cursor-pointer group">
            <input
              type="checkbox"
              className="w-3.5 h-3.5 rounded border-border bg-secondary accent-primary cursor-pointer"
              checked={filters.accessEmail}
              onChange={(e) => update("accessEmail", e.target.checked)}
            />
            <span className="text-[11px] font-semibold text-foreground group-hover:text-primary transition-colors">Access to email</span>
          </label>
          <TriState
            label="Changeable email"
            value={filters.changeableEmail}
            options={triStateOpts}
            onChange={(v) => update("changeableEmail", v as FilterState["changeableEmail"])}
          />
        </CollapsibleSection>

        <CollapsibleSection title="Linkability" icon="ri-links-line" sectionKey="linkability" openSections={openSections} onToggle={toggleSection}>
          <TriState
            label="Xbox linkable"
            value={filters.xbLinked}
            options={triStateLinkOpts}
            onChange={(v) => update("xbLinked", v as FilterState["xbLinked"])}
          />
          <TriState
            label="PSN linkable"
            value={filters.psnLinked}
            options={triStateLinkOpts}
            onChange={(v) => update("psnLinked", v as FilterState["psnLinked"])}
          />
        </CollapsibleSection>

        <CollapsibleSection title="Select Skins" icon="ri-crosshair-2-line" sectionKey="cosmetics-select" openSections={openSections} onToggle={toggleSection} />

        <CollapsibleSection title="Outfits &amp; Cosmetics" icon="ri-t-shirt-line" sectionKey="cosmetics" openSections={openSections} onToggle={toggleSection}>
          <RangeInput label="Outfits" fromPlaceholder="Min" toPlaceholder="Max" fromVal={filters.outfitsFrom} toVal={filters.outfitsTo} onFromChange={(v) => update("outfitsFrom", v)} onToChange={(v) => update("outfitsTo", v)} />
          <RangeInput label="Pickaxes" fromPlaceholder="Min" toPlaceholder="Max" fromVal={filters.pickaxesFrom} toVal={filters.pickaxesTo} onFromChange={(v) => update("pickaxesFrom", v)} onToChange={(v) => update("pickaxesTo", v)} />
          <RangeInput label="Dances" fromPlaceholder="Min" toPlaceholder="Max" fromVal={filters.dancesFrom} toVal={filters.dancesTo} onFromChange={(v) => update("dancesFrom", v)} onToChange={(v) => update("dancesTo", v)} />
          <RangeInput label="Gliders" fromPlaceholder="Min" toPlaceholder="Max" fromVal={filters.glidersFrom} toVal={filters.glidersTo} onFromChange={(v) => update("glidersFrom", v)} onToChange={(v) => update("glidersTo", v)} />
        </CollapsibleSection>

        <CollapsibleSection title="V-Bucks" icon="ri-copper-diamond-line" sectionKey="vbucks" openSections={openSections} onToggle={toggleSection}>
          <RangeInput label="V-Bucks balance" fromPlaceholder="Min" toPlaceholder="Max" fromVal={filters.vbucksFrom} toVal={filters.vbucksTo} onFromChange={(v) => update("vbucksFrom", v)} onToChange={(v) => update("vbucksTo", v)} />
        </CollapsibleSection>

        <CollapsibleSection title="Account Stats" icon="ri-bar-chart-2-line" sectionKey="stats" openSections={openSections} onToggle={toggleSection} />
        <CollapsibleSection title="Battle Pass" icon="ri-award-line" sectionKey="battlepass" openSections={openSections} onToggle={toggleSection} />
        <CollapsibleSection title="Other" icon="ri-more-2-fill" sectionKey="other" openSections={openSections} onToggle={toggleSection} />
      </div>
    </div>
  );
}