import { type ReactNode, useMemo, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { Link, Route, Switch, useLocation, useParams, Router as WouterRouter } from 'wouter';
import {
  Activity, ArrowLeft, ArrowUpRight, ArrowUpRightFromSquare, BookOpenCheck,
  ChevronDown, CircleAlert, Clock3, Database, FileCheck2, Globe2, GraduationCap,
  History, Landmark, ListFilter, LoaderCircle, Menu, Radio, RefreshCw, Search, ShieldCheck,
  SlidersHorizontal, Sparkles, X,
} from 'lucide-react';
import {
  getGetDashboardSummaryQueryKey,
  getListCrawlRunsQueryKey,
  getListScholarshipsQueryKey,
  useGetDashboardSummary,
  useGetScholarship,
  useHealthCheck,
  useListCrawlRuns,
  useListDemoChangeHistory,
  useListScholarships,
  useRunCrawler,
} from '@workspace/api-client-react';
import type { CrawlRun, DashboardSummary, DemoChange, Scholarship, ScholarshipDetail } from '@workspace/api-client-react';
import NotFound from '@/pages/not-found';
import { ErrorBoundary } from '@/components/error-boundary';

const queryClient = new QueryClient();

function date(value?: string | null, withTime = false) {
  if (!value) return 'Not recorded';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('en-IN', withTime
    ? { dateStyle: 'medium', timeStyle: 'short' }
    : { day: 'numeric', month: 'short', year: 'numeric' }).format(parsed);
}

function number(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat('en-IN').format(value) : '—';
}

function friendly(value?: string) {
  return (value || 'unknown').replace(/[_-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function sourceHost(url?: string) {
  try { return new URL(url || '').hostname.replace(/^www\./, ''); } catch { return 'Source unavailable'; }
}

function StatusTag({ value }: { value?: string }) {
  const normalized = (value || 'unknown').toLowerCase().replaceAll(' ', '-');
  return <span className={`tag tag-${normalized}`} data-testid={`status-${normalized}`}>{friendly(value)}</span>;
}

function SkeletonRows({ count = 4 }: { count?: number }) {
  return <div className="skeleton-stack" aria-label="Loading records" data-testid="loading-skeleton">
    {Array.from({ length: count }, (_, i) => <div className="skeleton-row" key={i}><i /><span /><span /></div>)}
  </div>;
}

function ErrorState({ retry, label = 'This data could not be loaded.' }: { retry: () => void; label?: string }) {
  return <div className="state-box state-error" role="alert" data-testid="state-error">
    <CircleAlert size={20} /><div><b>Connection interrupted</b><p>{label} Check the service and try again.</p></div>
    <button className="button button-outline button-small" onClick={retry} data-testid="button-retry"><RefreshCw size={14} /> Retry</button>
  </div>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="state-box state-empty" data-testid="state-empty">
    <div className="empty-symbol"><Database size={19} /></div><div><b>{title}</b><p>{detail}</p></div>
  </div>;
}

function RunButton({ compact = false }: { compact?: boolean }) {
  const client = useQueryClient();
  const crawler = useRunCrawler({
    mutation: {
      onSuccess: async () => {
        await Promise.all([
          client.invalidateQueries({ queryKey: getGetDashboardSummaryQueryKey() }),
          client.invalidateQueries({ queryKey: getListCrawlRunsQueryKey() }),
          client.invalidateQueries({ queryKey: getListScholarshipsQueryKey() }),
        ]);
      },
    },
  });
  return <div className="crawler-action">
    <button
      className={`button button-gold ${compact ? 'button-small' : ''}`}
      onClick={() => crawler.mutate()}
      disabled={crawler.isPending}
      data-testid="button-run-crawler"
    >
      {crawler.isPending ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
      {crawler.isPending ? 'Starting run…' : 'Run crawler'}
    </button>
    {crawler.isError && <span className="crawler-feedback crawler-error" role="alert" data-testid="status-crawler-error">Crawler request failed. Retry when the service is available.</span>}
    {crawler.isSuccess && <span className="crawler-feedback" role="status" data-testid="status-crawler-success">{crawler.data.message || `Run ${friendly(crawler.data.status).toLowerCase()} · ${date(crawler.data.startedAt, true)}`}</span>}
  </div>;
}

function Shell({ children }: { children: ReactNode }) {
  const [path] = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const health = useHealthCheck();
  const nav = [
    { href: '/', label: 'Overview', icon: Activity, exact: true },
    { href: '/scholarships', label: 'Scholarships', icon: GraduationCap },
    { href: '/crawl-runs', label: 'Crawl runs', icon: Radio },
  ];
  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
      <Link href="/" className="brand" data-testid="link-brand" onClick={() => setMobileOpen(false)}>
        <div className="brand-mark"><Landmark size={19} strokeWidth={1.8} /></div>
        <div className="brand-copy"><strong>Scholarship</strong><span>INTELLIGENCE</span></div>
      </Link>
      <div className="side-label">RESEARCH DESK</div>
      <nav className="side-nav" aria-label="Main navigation">
        {nav.map(({ href, label, icon: Icon, exact }) => {
          const active = exact ? path === '/' || path === '/dashboard' : path.startsWith(href);
          return <Link key={href} href={href} className={`nav-link ${active ? 'nav-active' : ''}`}
            data-testid={`link-nav-${label.toLowerCase().replace(' ', '-')}`} onClick={() => setMobileOpen(false)}>
            <Icon size={17} strokeWidth={1.8} /><span>{label}</span>{label === 'Scholarships' && <span className="nav-count">↗</span>}
          </Link>;
        })}
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-note">
        <div className="note-icon"><ShieldCheck size={17} /></div>
        <b>Evidence first</b>
        <p>Every surfaced detail links back to its official source.</p>
      </div>
      <div className="sidebar-footer">
        <span className={`health-dot ${health.isError ? 'health-down' : ''}`} />
        <span data-testid="status-service-health">{health.isLoading ? 'Checking service' : health.isError ? 'Service unavailable' : 'Data service'}</span>
        <span className="live-label">{health.isLoading ? '…' : health.isError ? 'OFFLINE' : 'CONNECTED'}</span>
      </div>
    </aside>
    {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <div className="main-column">
      <header className="topbar">
        <button className="mobile-menu" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Toggle navigation" data-testid="button-mobile-menu"><Menu size={19} /></button>
        <div className="breadcrumb"><span>Research desk</span><span className="crumb-slash">/</span><b>{path.startsWith('/scholarships/') ? 'Record detail' : path === '/scholarships' ? 'Scholarships' : path === '/crawl-runs' ? 'Crawl runs' : 'Overview'}</b></div>
        <div className="topbar-right"><span className="topbar-caption">INDIA · OFFICIAL SOURCES</span><span className="topbar-seal"><ShieldCheck size={17} /></span></div>
      </header>
      <main className="page-content">{children}</main>
      <footer className="app-footer"><span>Scholarship Intelligence</span><span>Source-led discovery for Indian students</span></footer>
    </div>
  </div>;
}

function PageHeading({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return <div className="page-heading">
    <div><div className="eyebrow"><span />{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>
    {actions && <div className="heading-actions">{actions}</div>}
  </div>;
}

function Stat({ label, value, note, icon: Icon, accent }: { label: string; value: ReactNode; note: string; icon: typeof Activity; accent?: boolean }) {
  return <section className={`stat-card ${accent ? 'stat-featured' : ''}`} data-testid={`metric-${label.toLowerCase().replaceAll(' ', '-')}`}>
    <div className="stat-top"><span>{label}</span><Icon size={17} /></div>
    <strong>{value}</strong><div className="stat-note">{note}</div>
  </section>;
}

function Dashboard() {
  const summaryQuery = useGetDashboardSummary();
  const runsQuery = useListCrawlRuns({ limit: 5 });
  const demoChangesQuery = useListDemoChangeHistory();
  const summary = summaryQuery.data as DashboardSummary | undefined;
  const runList = (runsQuery.data || []) as CrawlRun[];
  const demoChanges = (demoChangesQuery.data || []) as DemoChange[];
  return <div className="page">
    <PageHeading eyebrow="INTELLIGENCE OVERVIEW" title="A clearer view of opportunity." description="Verified scholarship information, grounded in official sources and continuously monitored." actions={<RunButton />} />
    {summaryQuery.isLoading ? <div className="stat-grid"><div className="stat-card stat-skeleton" /><div className="stat-card stat-skeleton" /><div className="stat-card stat-skeleton" /><div className="stat-card stat-skeleton" /></div>
      : summaryQuery.isError ? <ErrorState retry={() => summaryQuery.refetch()} label="Overview totals are unavailable." />
      : summary ? <div className="stat-grid">
        <Stat label="Discovered" value={number(summary.totalDiscovered)} note="Records in the index" icon={BookOpenCheck} accent />
        <Stat label="Verified" value={number(summary.verified)} note="Officially corroborated" icon={ShieldCheck} />
        <Stat label="Needs review" value={number(summary.reviewRequired)} note="Evidence needs attention" icon={FileCheck2} />
        <Stat label="Avg. confidence" value={`${number(summary.averageConfidence)}%`} note="Across discovered records" icon={Sparkles} />
      </div> : <EmptyState title="No overview available" detail="The service returned no summary data." />}
    <div className="dashboard-grid">
      <section className="panel activity-panel">
        <div className="panel-head"><div><div className="eyebrow">SYSTEM ACTIVITY</div><h2>Recent crawl activity</h2></div><Link className="text-link" href="/crawl-runs" data-testid="link-all-runs">All runs <ArrowUpRight size={15} /></Link></div>
        {runsQuery.isLoading ? <SkeletonRows count={3} /> : runsQuery.isError ? <ErrorState retry={() => runsQuery.refetch()} label="Recent crawl runs are unavailable." /> :
          runList.length ? <div className="run-list">{runList.slice(0, 4).map((run) => <RunRow run={run} key={run.id} />)}</div>
            : <EmptyState title="No crawl activity yet" detail="Run the crawler to check configured official sources. No records are shown until the service discovers them." />}
      </section>
      <aside className="panel signal-panel">
        <div className="signal-heading"><div className="signal-icon"><Globe2 size={18} /></div><span>PROVENANCE STANDARD</span></div>
        <h2>Trace every claim<br />to its origin.</h2>
        <p>Scholarship records are presented with source evidence, verification state, and a confidence breakdown—not just a headline score.</p>
        <div className="signal-rule" />
        <div className="signal-foot"><span><ShieldCheck size={15} /> Official-source evidence</span><span className="signal-index">01 / 03</span></div>
      </aside>
    </div>
    <section className="panel demo-change-panel" data-testid="demo-change-examples">
      <div className="panel-head">
        <div><div className="eyebrow">DEMO DATA · NOT REAL OPPORTUNITIES</div><h2>Example change history</h2></div>
        <span className="demo-badge">DEMO DATA</span>
      </div>
      <p className="demo-change-intro">Controlled deadline and award-amount changes are stored in a separate demo database. They do not alter or count toward live scholarship records.</p>
      {demoChangesQuery.isLoading ? <SkeletonRows count={2} /> : demoChangesQuery.isError ? <ErrorState retry={() => demoChangesQuery.refetch()} label="Demo change examples are unavailable." /> :
        demoChanges.length ? <div className="demo-change-grid">{demoChanges.map((change) => <article className="demo-change-card" key={change.id} data-testid={`demo-change-${change.fieldChanged}`}>
          <div className="demo-change-meta"><span>{friendly(change.fieldChanged)}</span><time>{date(change.dateDetected, true)}</time></div>
          <h3>{change.scholarshipName}</h3>
          <div className="demo-change-values"><span>{change.oldValue}</span><ArrowUpRight size={14} /><b>{change.newValue}</b></div>
          <p>{change.evidence}</p>
          <a href={change.sourceUrl} target="_blank" rel="noreferrer" className="inline-source">{sourceHost(change.sourceUrl)} <ArrowUpRightFromSquare size={12} /></a>
        </article>)}</div> : <EmptyState title="No demo examples yet" detail="Run the isolated change simulator to generate labeled deadline and amount examples." />}
    </section>
    <section className="panel latest-panel">
      <div className="panel-head"><div><div className="eyebrow">LATEST DISCOVERIES</div><h2>Recently indexed opportunities</h2></div><Link className="text-link" href="/scholarships" data-testid="link-browse-scholarships">Browse scholarships <ArrowUpRight size={15} /></Link></div>
      <ScholarshipTable compact />
    </section>
  </div>;
}

function ScholarshipTable({ compact = false, params }: { compact?: boolean; params?: Record<string, string | number | undefined> }) {
  const query = useListScholarships(params);
  const scholarships = (query.data || []) as Scholarship[];
  if (query.isLoading) return <SkeletonRows count={compact ? 3 : 6} />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} label="Scholarship records are unavailable." />;
  if (!scholarships.length) return <EmptyState title="No matching records" detail={compact ? 'No scholarship records have been indexed yet. The crawler has not supplied records to display.' : 'No official-source records match these filters. Adjust the search or clear a filter to explore the index.'} />;
  return <div className="table-wrap" data-testid="scholarship-table">
    <table><thead><tr><th>OPPORTUNITY</th><th>PROVIDER</th><th>BENEFIT</th><th>DEADLINE</th><th>CONFIDENCE</th><th>STATUS</th><th /></tr></thead>
      <tbody>{scholarships.map((scholarship) => <tr key={scholarship.id} data-testid={`row-scholarship-${scholarship.id}`}>
        <td><Link className="record-link" href={`/scholarships/${encodeURIComponent(scholarship.id)}`} data-testid={`link-scholarship-${scholarship.id}`}><strong>{scholarship.scholarshipName}</strong><span>{scholarship.educationLevel || 'Education level not specified'} · {sourceHost(scholarship.officialSourceUrl)}</span></Link></td>
        <td className="provider-cell">{scholarship.provider || 'Not specified'}</td>
        <td className="benefit-cell">{scholarship.amount || scholarship.benefit || 'Not stated'}</td>
        <td className="date-cell">{scholarship.closingDate ? date(scholarship.closingDate) : 'Not stated'}</td>
        <td><Confidence value={scholarship.confidenceScore} /></td>
        <td><StatusTag value={scholarship.verificationStatus} /></td>
        <td><Link href={`/scholarships/${encodeURIComponent(scholarship.id)}`} className="row-open" aria-label={`View ${scholarship.scholarshipName}`} data-testid={`button-open-scholarship-${scholarship.id}`}><ArrowUpRight size={16} /></Link></td>
      </tr>)}</tbody>
    </table>
    {!compact && <div className="table-foot"><span>{number(scholarships.length)} records returned by the source service</span><span>Values are source-reported; inspect evidence for context.</span></div>}
  </div>;
}

function Confidence({ value }: { value: number }) {
  const safe = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
  return <div className="confidence" data-testid="text-confidence"><div className="confidence-track"><span style={{ width: `${safe}%` }} /></div><b>{number(value)}<small>%</small></b></div>;
}

function Scholarships() {
  const [search, setSearch] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState({ sourceType: '', status: '', verificationStatus: '', educationLevel: '', category: '', domicile: '', minConfidence: '', maxConfidence: '' });
  const params = useMemo(() => ({
    q: search.trim() || undefined,
    ...Object.fromEntries(Object.entries(filters).map(([key, val]) => [key, key.includes('Confidence') ? (val ? Number(val) : undefined) : val || undefined])),
  }), [search, filters]);
  const setFilter = (key: keyof typeof filters, value: string) => setFilters((current) => ({ ...current, [key]: value }));
  const clear = () => { setSearch(''); setFilters({ sourceType: '', status: '', verificationStatus: '', educationLevel: '', category: '', domicile: '', minConfidence: '', maxConfidence: '' }); };
  const activeCount = Object.values(filters).filter(Boolean).length;
  return <div className="page">
    <PageHeading eyebrow="OPPORTUNITY INDEX" title="Scholarships" description="Search the records discovered from official scholarship sources." actions={<span className="source-caveat"><ShieldCheck size={14} /> No illustrative records</span>} />
    <section className="panel search-panel">
      <div className="search-row">
        <div className="search-input-wrap"><Search size={18} /><input aria-label="Search scholarships" placeholder="Search name, provider, eligibility…" value={search} onChange={(event) => setSearch(event.target.value)} data-testid="input-scholarship-search" />
          {search && <button className="clear-search" aria-label="Clear search" onClick={() => setSearch('')} data-testid="button-clear-search"><X size={15} /></button>}</div>
        <button className={`button button-outline filter-toggle ${filtersOpen ? 'filter-on' : ''}`} onClick={() => setFiltersOpen((open) => !open)} data-testid="button-toggle-filters"><SlidersHorizontal size={16} /> Filters {activeCount > 0 && <span className="filter-count">{activeCount}</span>}<ChevronDown size={14} /></button>
      </div>
      {filtersOpen && <div className="filter-grid" data-testid="filters-panel">
        <FilterSelect label="Source type" value={filters.sourceType} onChange={(v) => setFilter('sourceType', v)} options={['government', 'university', 'foundation']} />
        <FilterSelect label="Current status" value={filters.status} onChange={(v) => setFilter('status', v)} options={['ACTIVE', 'EXPIRING_SOON', 'EXPIRED', 'REVIEW_REQUIRED', 'NO_LONGER_VERIFIABLE']} />
        <FilterSelect label="Verification" value={filters.verificationStatus} onChange={(v) => setFilter('verificationStatus', v)} options={['VERIFIED', 'REVIEW_REQUIRED']} />
        <FilterSelect label="Education level" value={filters.educationLevel} onChange={(v) => setFilter('educationLevel', v)} options={['school', 'undergraduate', 'postgraduate', 'doctoral', 'professional']} />
        <label className="filter-label">Category<input value={filters.category} onChange={(e) => setFilter('category', e.target.value)} placeholder="e.g. SC, OBC" data-testid="input-filter-category" /></label>
        <label className="filter-label">Domicile<input value={filters.domicile} onChange={(e) => setFilter('domicile', e.target.value)} placeholder="State or territory" data-testid="input-filter-domicile" /></label>
        <label className="filter-label">Confidence from<input type="number" min="0" max="100" value={filters.minConfidence} onChange={(e) => setFilter('minConfidence', e.target.value)} placeholder="0" data-testid="input-confidence-min" /></label>
        <label className="filter-label">Confidence to<input type="number" min="0" max="100" value={filters.maxConfidence} onChange={(e) => setFilter('maxConfidence', e.target.value)} placeholder="100" data-testid="input-confidence-max" /></label>
        <button className="text-link clear-filters" onClick={clear} data-testid="button-clear-filters"><X size={14} /> Clear all filters</button>
      </div>}
    </section>
    <div className="results-strip"><span><ListFilter size={15} /> {search || activeCount ? 'Filtered results' : 'All indexed opportunities'}</span><span>Search results reflect service data only</span></div>
    <section className="panel results-panel"><ScholarshipTable params={params} /></section>
  </div>;
}

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  const id = label.toLowerCase().replaceAll(' ', '-');
  return <label className="filter-label">{label}<select value={value} onChange={(event) => onChange(event.target.value)} data-testid={`select-filter-${id}`}>
    <option value="">Any</option>{options.map((option) => <option value={option} key={option}>{friendly(option)}</option>)}
  </select></label>;
}

function DetailPage() {
  const params = useParams<{ scholarshipId: string }>();
  const id = params.scholarshipId || '';
  const query = useGetScholarship(id);
  const item = query.data as ScholarshipDetail | undefined;
  if (query.isLoading) return <div className="page"><Link className="back-link" href="/scholarships" data-testid="link-back-scholarships"><ArrowLeft size={15} /> Back to scholarships</Link><SkeletonRows count={7} /></div>;
  if (query.isError) return <div className="page"><Link className="back-link" href="/scholarships" data-testid="link-back-scholarships"><ArrowLeft size={15} /> Back to scholarships</Link><ErrorState retry={() => query.refetch()} label="This scholarship record is unavailable." /></div>;
  if (!item) return <div className="page"><Link className="back-link" href="/scholarships" data-testid="link-back-scholarships"><ArrowLeft size={15} /> Back to scholarships</Link><EmptyState title="Record not found" detail="The service did not return a scholarship for this identifier." /></div>;
  return <div className="page">
    <Link className="back-link" href="/scholarships" data-testid="link-back-scholarships"><ArrowLeft size={15} /> Back to scholarships</Link>
    <div className="detail-hero">
      <div className="detail-hero-main"><div className="eyebrow"><span />SCHOLARSHIP RECORD · {item.sourceType || 'SOURCE TYPE NOT SET'}</div><h1 data-testid="text-scholarship-name">{item.scholarshipName}</h1><p className="detail-provider">{item.provider || 'Provider not specified'}</p>
        <div className="detail-tags"><StatusTag value={item.currentStatus} /><StatusTag value={item.verificationStatus} /><span className="tag tag-neutral"><Clock3 size={12} /> Verified {date(item.lastVerified)}</span></div>
      </div>
      <div className="detail-score"><span>CONFIDENCE</span><strong>{number(item.confidenceScore)}<small>%</small></strong><Confidence value={item.confidenceScore} /></div>
    </div>
    <div className="detail-layout">
      <div className="detail-main">
        <section className="panel detail-section">
          <SectionTitle kicker="01 / OPPORTUNITY" title="At a glance" />
          <div className="overview-highlight"><div className="highlight-icon"><GraduationCap size={18} /></div><div><span>AWARD / BENEFIT</span><b>{item.amount || item.benefit || 'Not stated by source'}</b></div></div>
          <div className="field-grid">
            <Field label="Benefit details" value={item.benefit} /><Field label="Education level" value={item.educationLevel} />
            <Field label="Application opens" value={date(item.openingDate)} /><Field label="Application closes" value={date(item.closingDate)} />
            <Field label="Current status" value={item.currentStatus} /><Field label="Verification" value={item.verificationStatus} />
          </div>
        </section>
        <section className="panel detail-section">
          <SectionTitle kicker="02 / ELIGIBILITY" title="Who can apply" />
          <div className="field-grid">
            <Field label="Eligibility" value={item.eligibility} wide /><Field label="Academic requirements" value={item.academicRequirements} />
            <Field label="Course requirements" value={item.courseRequirements} /><Field label="Income criteria" value={item.incomeCriteria} />
            <Field label="Age criteria" value={item.ageCriteria} /><Field label="Gender criteria" value={item.genderCriteria} />
            <Field label="Category criteria" value={item.categoryCriteria} /><Field label="Domicile" value={item.domicileRequirements} />
            <Field label="Institution requirements" value={item.institutionRequirements} wide />
          </div>
        </section>
        <section className="panel detail-section">
          <SectionTitle kicker="03 / APPLICATION" title="Requirements & process" />
          <div className="field-grid"><Field label="Documents required" value={item.documentsRequired} wide /><Field label="Selection process" value={item.selectionProcess} /><Field label="Renewal requirements" value={item.renewalRequirements} /></div>
          <div className="link-row">
            <a href={item.officialSourceUrl} target="_blank" rel="noreferrer" className="source-link" data-testid="link-official-source"><Globe2 size={16} /><span><b>Official source</b><small>{sourceHost(item.officialSourceUrl)}</small></span><ArrowUpRightFromSquare size={15} /></a>
            <a href={item.applicationUrl} target="_blank" rel="noreferrer" className="source-link" data-testid="link-application"><ArrowUpRight size={16} /><span><b>Application page</b><small>{sourceHost(item.applicationUrl)}</small></span><ArrowUpRightFromSquare size={15} /></a>
          </div>
        </section>
        <section className="panel detail-section evidence-section">
          <SectionTitle kicker="04 / PROVENANCE" title="Field-level evidence" trailing={<span className="section-count">{item.evidence?.length || 0} sources</span>} />
          <p className="section-intro">Extracted values are paired with captured official-source text. Empty evidence means no supporting passage was returned for this record.</p>
          {item.evidence?.length ? <div className="evidence-list">{item.evidence.map((evidence) => <article className="evidence-card" key={evidence.id} data-testid={`evidence-${evidence.id}`}>
            <div className="evidence-top"><span className="field-chip">{friendly(evidence.fieldName)}</span><a href={evidence.sourceUrl} target="_blank" rel="noreferrer" data-testid={`link-evidence-source-${evidence.id}`}>{sourceHost(evidence.sourceUrl)} <ArrowUpRightFromSquare size={12} /></a></div>
            <div className="evidence-value"><span>EXTRACTED VALUE</span><b>{evidence.extractedValue || 'No extracted value'}</b></div>
            <blockquote>{evidence.evidenceText || 'No source passage was captured.'}</blockquote>
            <div className="evidence-date">Captured {date(evidence.capturedAt, true)}</div>
          </article>)}</div> : <EmptyState title="No field evidence returned" detail="This record currently has no evidence passages attached. Treat its fields as uncorroborated until source evidence is available." />}
        </section>
        <section className="panel detail-section">
          <SectionTitle kicker="05 / CHANGE TRACKING" title="Change history" trailing={<span className="section-count">{item.changeHistory?.length || 0} changes</span>} />
          {item.changeHistory?.length ? <div className="timeline">{item.changeHistory.map((change) => <article className="change-entry" key={change.id} data-testid={`change-${change.id}`}>
            <div className="timeline-mark">{change.isDemo ? <Sparkles size={13} /> : <History size={13} />}</div>
            <div className="change-content"><div className="change-meta"><b>{friendly(change.fieldChanged)}</b><span>{date(change.dateDetected, true)}</span>{change.isDemo && <span className="demo-badge">DEMO</span>}</div>
              <div className="change-diff"><span>{change.oldValue || 'Not recorded'}</span><ArrowUpRight size={14} /><b>{change.newValue || 'Not recorded'}</b></div>
              <p>{change.evidence || 'No change evidence provided.'}</p><a href={change.sourceUrl} target="_blank" rel="noreferrer" className="inline-source" data-testid={`link-change-source-${change.id}`}>{sourceHost(change.sourceUrl)} <ArrowUpRightFromSquare size={12} /></a></div>
          </article>)}</div> : <EmptyState title="No changes recorded" detail="No field changes have been reported for this record." />}
        </section>
      </div>
      <aside className="detail-aside">
        <section className="panel score-panel">
          <div className="eyebrow">SCORING TRANSPARENCY</div><h2>How confidence<br />was assessed</h2>
          <p className="score-description">The score breakdown below is supplied by the service. It is not a measure of eligibility.</p>
          {item.scoreBreakdown?.length ? <div className="score-list">{item.scoreBreakdown.map((score, i) => <div className="score-item" key={`${score.label}-${i}`} data-testid={`score-item-${i}`}>
            <div className="score-label"><b>{score.label}</b><span>{number(score.earned)}<small> / {number(score.points)}</small></span></div><div className="score-track"><span style={{ width: `${score.points > 0 ? Math.max(0, Math.min(100, score.earned / score.points * 100)) : 0}%` }} /></div><p>{score.reason}</p>
          </div>)}</div> : <EmptyState title="No scoring rationale" detail="The service did not provide score components for this record." />}
          <div className="score-total"><span>OVERALL CONFIDENCE</span><b>{number(item.confidenceScore)}<small>%</small></b></div>
        </section>
        <section className="panel metadata-panel"><div className="eyebrow">RECORD METADATA</div>
          <Meta label="Last verified" value={date(item.lastVerified, true)} /><Meta label="Created" value={date(item.createdAt, true)} /><Meta label="Last updated" value={date(item.updatedAt, true)} />
          <Meta label="Record ID" value={item.id} mono />
        </section>
        <div className="trust-note"><ShieldCheck size={16} /><p><b>Verification is not endorsement.</b> Confirm eligibility and deadlines on the official source before applying.</p></div>
      </aside>
    </div>
  </div>;
}

function SectionTitle({ kicker, title, trailing }: { kicker: string; title: string; trailing?: ReactNode }) {
  return <div className="section-title"><div><div className="eyebrow">{kicker}</div><h2>{title}</h2></div>{trailing}</div>;
}
function Field({ label, value, wide = false }: { label: string; value?: string; wide?: boolean }) {
  return <div className={`field ${wide ? 'field-wide' : ''}`} data-testid={`field-${label.toLowerCase().replaceAll(' ', '-')}`}><span>{label}</span><p>{value || 'Not provided by source'}</p></div>;
}
function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="meta-row"><span>{label}</span><b className={mono ? 'mono' : ''}>{value}</b></div>;
}

function RunRow({ run }: { run: CrawlRun }) {
  return <div className="run-row" data-testid={`run-row-${run.id}`}>
    <div className="run-status-mark"><RefreshCw size={14} /></div>
    <div className="run-row-main"><div><b>{friendly(run.status)} crawl</b><span>{date(run.startedAt, true)}</span></div><p>{run.message || 'No run message provided.'}</p></div>
    <div className="run-count"><b>{number(run.discoveredCount)}</b><span>FOUND</span></div>
    <StatusTag value={run.status} />
  </div>;
}

function CrawlRuns() {
  const query = useListCrawlRuns({ limit: 50 });
  const runs = (query.data || []) as CrawlRun[];
  return <div className="page">
    <PageHeading eyebrow="MONITORING" title="Crawl runs" description="A transparent record of checks against configured official sources." actions={<RunButton />} />
    <section className="run-summary-band"><div><span className="band-icon"><Radio size={17} /></span><span><b>Source monitoring</b><small>Run history reported by the crawler service</small></span></div><span className="band-note"><span className="health-dot" /> Live service data</span></section>
    <section className="panel runs-panel"><div className="panel-head"><div><div className="eyebrow">EXECUTION HISTORY</div><h2>Recent runs</h2></div><span className="records-label">{query.isLoading ? 'Loading…' : `${number(runs.length)} runs returned`}</span></div>
      {query.isLoading ? <SkeletonRows count={6} /> : query.isError ? <ErrorState retry={() => query.refetch()} label="Crawl history is unavailable." /> :
        runs.length ? <div className="run-table">{runs.map((run) => <div className="run-detail-row" key={run.id} data-testid={`crawl-run-${run.id}`}>
          <div className="run-detail-status"><span className={`run-indicator indicator-${(run.status || '').toLowerCase()}`} /><div><b>{friendly(run.status)}</b><span>{run.message || 'No message reported'}</span></div></div>
          <div className="run-stat"><small>STARTED</small><b>{date(run.startedAt, true)}</b></div><div className="run-stat"><small>COMPLETED</small><b>{date(run.completedAt, true)}</b></div>
          <div className="run-metrics">{[['Found', run.discoveredCount], ['New', run.newCount], ['Updated', run.updatedCount], ['Changed', run.changedCount], ['Expired', run.expiredCount], ['Failed', run.failedCount]].map(([label, value]) => <div key={String(label)}><b>{number(Number(value))}</b><small>{label}</small></div>)}</div>
        </div>)}</div> : <EmptyState title="No runs recorded" detail="There is no crawler history from the service yet. Start a crawl to check the configured official sources." />}
    </section>
    <p className="runs-disclaimer"><ShieldCheck size={14} /> Counts and status are reported by the crawler. A successful run does not imply every field has been verified.</p>
  </div>;
}

function Router() {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}><Shell><Switch>
    <Route path="/" component={Dashboard} />
    <Route path="/dashboard" component={Dashboard} />
    <Route path="/scholarships" component={Scholarships} />
    <Route path="/scholarships/:scholarshipId" component={DetailPage} />
    <Route path="/crawl-runs" component={CrawlRuns} />
    <Route component={NotFound} />
  </Switch></Shell></ErrorBoundary>;
}

function App() {
  return <QueryClientProvider client={queryClient}><WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}><Router /></WouterRouter></QueryClientProvider>;
}

export default App;
