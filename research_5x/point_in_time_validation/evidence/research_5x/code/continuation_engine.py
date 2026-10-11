"""Small source-audited adapter for delayed fills and holding-rule ablations.

The 10 October engine remains unchanged. This adapter transforms only four
identified AST locations in its simulate function, and exposes its own
callable. Default settings must reproduce every baseline numeric result.
"""
import ast, bisect, copy, inspect
from collections import defaultdict
import run_research as base

EXPECTED_BASE_SHA='a46271c5436a9fdec93af55705623a270c2888b0124814cf90af873d54ecf7b5'
if base.sha(base.Path(base.__file__))!=EXPECTED_BASE_SHA:
    raise RuntimeError('Continuation adapter requires the frozen October 10 engine')

SOURCE=inspect.getsource(base.simulate)
tree=ast.parse(SOURCE)
function=tree.body[0]
def statements(s):return ast.parse(s).body
def expression(s):return ast.parse(s,mode='eval').body
class Adapter(ast.NodeTransformer):
    def __init__(self):self.counts=defaultdict(int)
    def visit_Assign(self,node):
        self.generic_visit(node)
        if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='pending' and isinstance(node.value,ast.Constant) and node.value.value is None:
            # Initial pending=None and consumption pending=None are distinct:
            # only initialize the schedule at function scope (handled below).
            return node
        if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='pending' and isinstance(node.value,ast.Tuple):
            self.counts['schedule']=self.counts['schedule']+1
            return statements("""
due_index=calendar.index(ds)+1+int(cfg.get('delay_sessions',0))
due=calendar[due_index] if due_index<len(calendar) else None
signals[-1]['scheduled_fill_date']=due
signals[-1]['additional_delay_sessions']=int(cfg.get('delay_sessions',0))
signals[-1]['holding_rule']=cfg.get('holding_rule','rebalance')
if due is not None and due<=end:
    scheduled[due]=(targets,list(w),bool(cfg.get('sticky') or cfg.get('preserve_weights')))
""")
        return node
    def visit_If(self,node):
        self.generic_visit(node)
        if ast.unparse(node.test)=="cfg.get('sticky')":
            self.counts['retention']+=1
            node.test=expression("cfg.get('sticky') or cfg.get('retain_rank35')")
        if isinstance(node.test,ast.Name) and node.test.id=='pending':
            self.counts['dispatch']+=1
            return statements("""
pending=scheduled.pop(ds,None)
if pending and int(cfg.get('delay_sessions',0))>0:
    # Eligibility is known by the fill date. Removed names are left as cash;
    # do not replace them using later rankings or future returns.
    active=set(start_members)
    for event in membership_changes:
        if event['date']>ds:break
        active.discard(event.get('removed'))
        if event.get('added'):active.add(event['added'])
    old_targets,old_weights,is_sticky=pending
    keep=[(s,w) for s,w in zip(old_targets,old_weights) if s in active]
    suppressed.extend({'date':ds,'ticker':s,'reason':'not a member at delayed fill'} for s in old_targets if s not in active)
    pending=([s for s,w in keep],[w for s,w in keep],is_sticky)
""")+[node]
        return node

adapter=Adapter()
function=adapter.visit(function)
# Insert schedule state after the original opening initialization.
function.body[1:1]=statements("""
scheduled={}
suppressed=[]
raw_membership=load_gz(REPO/'backtests/staged/wf3_prices.json.gz')
start_members,membership_changes=membership(raw_membership)
if int(cfg.get('delay_sessions',0))<0:raise ValueError('Delay must be nonnegative')
if cfg.get('inverse_vol') and cfg.get('preserve_weights'):
    raise ValueError('Weight-drift ablation is restricted to equal-entry-weight candidates')
""")
# Record suppressed delayed entries without changing the base metric schema.
return_node=function.body[-1]
if not isinstance(return_node,ast.Return):raise RuntimeError('Unexpected base return structure')
function.body[-1:-1]=statements("result['suppressed_delayed_entries']=suppressed")
ast.fix_missing_locations(tree)
if dict(adapter.counts)!={'dispatch':1,'retention':1,'schedule':1}:
    raise RuntimeError('Unexpected adapter locations: '+str(dict(adapter.counts)))
namespace=dict(base.__dict__)
exec(compile(tree,'continuation_simulate','exec'),namespace)
simulate=namespace['simulate']
TRANSFORMED_SOURCE=ast.unparse(tree)+'\n'

def benchmark_window(frames,calendar,start,end,cost_bps=20):
    """Freshly funded SPY, whole shares, explicit dividends, marked ending NAV."""
    f=frames['SPY'];dates=[d for d in calendar if start<=d<=end]
    px=float(f.loc[dates[0],'raw_open'])
    qty=base.math.floor(base.CAPITAL/px/(1+cost_bps/10000))
    cash=base.CAPITAL-qty*px*(1+cost_bps/10000);rows=[]
    for ds in dates:
        cash+=qty*float(f.loc[ds,'dividend'])
        rows.append({'date':ds,'equity':cash+qty*float(f.loc[ds,'raw_close']),'cash':cash})
    curve=base.pd.DataFrame(rows);a=curve.equity.to_numpy()
    result={'start':start,'end':dates[-1],'net_return_pct':(a[-1]/base.CAPITAL-1)*100,
        'max_dd_pct':float(base.np.min(a/base.np.maximum.accumulate(base.np.r_[base.CAPITAL,a])[1:]-1)*100),
        'shares':qty,'cost_bps_entry':cost_bps,'policy':'buy at first open; whole shares; cash dividends; terminal mark without exit cost'}
    return result,curve
