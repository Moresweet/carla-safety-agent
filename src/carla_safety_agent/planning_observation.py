"""Observe existing PID calls; never run extra inference or change chosen controls."""
from copy import deepcopy


class PlanningObservation:
    def __init__(self,agent):
        self.agent=agent
        self.owner=next((owner for owner in (getattr(agent,'net',None),getattr(agent,'pidcontroller',None),getattr(agent,'model',None))
                         if callable(getattr(owner,'control_pid',None))),None)
        self.outputs=None
        self.anchor=None
        self.calls=0

    def run_step(self,inputs,elapsed,*,frame,timestamp,ego_matrix,runner=None):
        # Wrappers pass the bound base implementation to avoid recursive entry.
        run = runner if runner is not None else self.agent.run_step
        if self.owner is None:
            return run(inputs,elapsed)
        original=self.owner.control_pid
        def observe(*args,**kwargs):
            result=original(*args,**kwargs)
            if isinstance(result,(tuple,list)) and len(result)==4 and isinstance(result[3],dict):
                # Keep the returned mapping until run_step finishes: VAD/UniAD
                # append their full plan to this same controller metadata object.
                self.outputs=result[3]
                self.anchor={'frame':frame,'model_step':getattr(self.agent,'step',None),
                             'timestamp':timestamp,'ego_matrix':deepcopy(ego_matrix)}
                navigation=getattr(self.agent,'_planning_navigation_reference',None)
                if isinstance(navigation,dict) and navigation.get('model_step')==self.anchor['model_step']:
                    self.anchor['navigation_reference']=deepcopy(navigation)
                self.calls+=1
            return result
        self.owner.control_pid=observe
        try:
            return run(inputs,elapsed)
        finally:
            self.owner.control_pid=original

    def snapshot(self):
        warmup=getattr(self.agent,'data_queue_len',getattr(getattr(self.agent,'config',None),'seq_len',None))
        return {'state':'observed' if self.anchor else 'not_emitted_yet',
                'outputs':self.outputs,'anchor':self.anchor,'calls':self.calls,'warmup_steps':warmup}
