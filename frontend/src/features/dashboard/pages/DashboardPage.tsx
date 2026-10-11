import { useEffect, useState } from 'react';
import { type ScreenKey } from '../../../components/layout/AppShell';
import { Header, Icon, Notice, Busy, StatusPill } from '../../../components/ui/Elements';
import { apiRequest, type User } from '../../../lib/authApi';
import { type Evaluation, dateDisplay, percent } from '../../../lib/evaluations';

type Props = { onNavigate: (screen: ScreenKey) => void; user: User; refresh: number; onSelect: (id: number) => void };
export function DashboardPage({ onNavigate, user, refresh, onSelect }: Props) {
  const [items, setItems] = useState<Evaluation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => { let active = true; setLoading(true); apiRequest<Evaluation[]>('/evaluations').then(data => { if (active) { setItems(data); setError(''); } }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [refresh]);
  const cards: { key: ScreenKey; title: string; copy: string; icon: string }[] = [
    { key: 'analysis', title: 'New test-mill evaluation', copy: 'Record lot details, weigh rice fractions, and upload a sample image.', icon: 'analysis' },
    { key: 'history', title: 'Assessment history', copy: 'Find previous test runs and revisit saved measurements.', icon: 'history' },
    { key: 'reports', title: 'Evaluation reports', copy: 'View report availability and saved screening records.', icon: 'reports' },
    { key: 'profile', title: 'Account settings', copy: 'Update your profile and secure your account.', icon: 'profile' },
  ];
  return <><Header eyebrow="OVERVIEW" title={`Good to see you, ${user.full_name.split(' ')[0] || 'there'}.`} description="Your test-milling workspace, organized in one place." actions={<button className="button button-primary" onClick={() => onNavigate('analysis')}><Icon name="analysis" size={18}/>New evaluation</button>}/>
    <Notice><strong>ML integration pending.</strong> The system can save assessments and calculate physical milling recovery. Image classification, DSS recommendations, and final evaluation reports are not yet enabled.</Notice>
    {error && <Notice tone="warning">{error}</Notice>}
    <section className="stats-grid" aria-label="Assessment summary"><div className="stat-card"><span>Total test runs</span><strong>{loading ? '—' : items.length}</strong><small>Saved assessments</small></div><div className="stat-card"><span>Awaiting screening</span><strong>{loading ? '—' : items.filter(i => i.status === 'awaiting_model').length}</strong><small>Awaiting ML integration</small></div><div className="stat-card"><span>Completed quality reports</span><strong>0</strong><small>No ML results generated</small></div></section>
    <div className="section-header"><div><h2>Quick actions</h2><p>Choose what you want to work on.</p></div></div>
    <div className="quick-grid">{cards.map(card => <button key={card.key} className="quick-card" onClick={() => onNavigate(card.key)}><span className="quick-icon"><Icon name={card.icon} size={24}/></span><strong>{card.title}</strong><span>{card.copy}</span><span className="quick-more">Open <Icon name="arrow" size={16}/></span></button>)}</div>
    <section className="panel recent-panel"><div className="section-header"><div><h2>Recent test runs</h2><p>Your latest saved assessments.</p></div><button className="text-button" onClick={() => onNavigate('history')}>View all <Icon name="arrow" size={15}/></button></div>
      {loading ? <Busy/> : items.length ? <div className="record-list">{items.slice(0, 4).map(item => <button className="record-row" key={item.id} onClick={() => onSelect(item.id)}><div className="record-badge"><Icon name="chart"/></div><div className="record-main"><strong>{item.lot_id} <span className="subtle">/ {item.test_run_id}</span></strong><span>{dateDisplay(item.test_date)} · Total recovery {percent(item.total_milling_recovery)}</span></div><StatusPill>Awaiting model</StatusPill><Icon name="arrow" size={18}/></button>)}</div> : <div className="compact-empty">No test runs yet. <button className="text-button" onClick={() => onNavigate('analysis')}>Create your first evaluation</button>.</div>}
    </section></>;
}
