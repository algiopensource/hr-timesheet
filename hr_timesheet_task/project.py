# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright (c) 2010 Camptocamp SA (http://www.camptocamp.com) 
# All Right Reserved
#
# Author : Joel Grand-guillaume (Camptocamp)
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

import time
from datetime import datetime
import netsvc
from osv import fields
from osv import osv
from tools import config
import decimal_precision as dp


####################################################################################
#  Project Task
# ####################################################################################
class task(osv.osv):
    
    _inherit = "project.task"
    
    def search(self, cr, uid, args, offset=0, limit=None, order=None, context=None, count=False):
        """Check if we are from project.task.work, if yes, look into the related analytic account
        of the project."""
        project_ids = []
        if context is None:
            context = {}
        if context.get('account_id' ,False):
            proj_obj = self.pool.get('project.project')
            # Take the related projects
            project_ids = proj_obj.search(cr, uid, 
                                          [('analytic_account_id', '=', context.get('account_id',False))])
            if project_ids:
                args.append(('project_id', 'in', project_ids))
                        
        return super(task, self).search(cr, uid, args, offset, limit,
                                        order, context=context, count=count)
        
    def name_search(self, cr, user, name, args=None, operator='ilike', context=None, limit=100):
        if not args:
            args = []
        if context is None:
            context = {}
        ids = []
        if not ids:
            ids = self.search(cr, user, [('name', operator, name)] + args, 
                              limit=limit, context=context)
        return self.name_get(cr, user, ids, context)
    
    # Compute: effective_hours, total_hours, progress
    def _hours_get(self, cr, uid, ids, field_names, args, context=None):
    # FIXME : Here, we're also not doing the UoM conversion. We consider all is hours...
        res = {}
        for task in self.browse(cr, uid, ids, context=context):
            work_hours = reduce(lambda memo, work: memo + work.hours, task.work_ids, 0.0)
            deduced_hours = reduce(lambda memo, work: memo + work.hours_to_inv, task.work_ids, 0.0)

            res[task.id] = {'effective_hours': work_hours,
                            'deduced_hours' : deduced_hours,
                            'total_hours': (task.remaining_hours or 0.0) + deduced_hours}

            res[task.id]['delay_hours'] = res[task.id]['total_hours'] - task.planned_hours
            res[task.id]['progress'] = 0.0
            if task.remaining_hours + deduced_hours:
                res[task.id]['progress'] = round(min(100.0 * deduced_hours / res[task.id]['total_hours'], 99.99),2)
            if task.state in ('done','cancelled'):
                res[task.id]['progress'] = 100.0

        return res

    def _get_task(self, cr, uid, ids, context=None):
        result = {}
        lines = self.pool.get('hr.analytic.timesheet').read(cr, uid, ids, ['id','task_id'], context=context)
        for line in lines:
            if 'task_id' in line and line['task_id']: 
                result[line['task_id'][0]] = True
        return result.keys()
        
    def _get_analytic_line(self,cr,uid,ids,context=None):
        ts_line_obj = self.pool.get('hr.analytic.timesheet')
        ts_ids = ts_line_obj.search(cr,uid,[('line_id','in',ids)])
        return self.pool.get('project.task')._get_task(cr,uid,ts_ids,context)
        
    _columns = {
        'work_ids': fields.one2many('hr.analytic.timesheet', 'task_id', 'Work done'),
        'effective_hours': fields.function(_hours_get, method=True, string='Hours Spent', multi='hours', help="Computed using the sum of the task work done.",
            store = {
                'project.task': (lambda self, cr, uid, ids, c={}: ids, ['work_ids', 'remaining_hours', 'planned_hours'], 10),
                'hr.analytic.timesheet': (_get_task, ['task_id','unit_amount','product_uom_id','to_invoice'], 10),
                'account.analytic.line': (_get_analytic_line, ['product_uom_id','unit_amount','to_invoice'], 10),
            }),
        'deduced_hours': fields.function(_hours_get, method=True, string='Deduced hours', multi='hours', help="Computed using the sum of the task work done with invoice factor.",
            store = {
                'project.task': (lambda self, cr, uid, ids, c={}: ids, ['work_ids', 'remaining_hours', 'planned_hours'], 10),
                'hr.analytic.timesheet': (_get_task, ['task_id','unit_amount','product_uom_id','to_invoice'], 10),
                'account.analytic.line': (_get_analytic_line, ['product_uom_id','unit_amount','to_invoice'], 10),
            }),
        'total_hours': fields.function(_hours_get, method=True, string='Total Hours', multi='hours', help="Computed as: Time Spent + Remaining Time.",
            store = {
                'project.task': (lambda self, cr, uid, ids, c={}: ids, ['work_ids', 'remaining_hours', 'planned_hours'], 10),
                'hr.analytic.timesheet': (_get_task, ['task_id','unit_amount','product_uom_id','to_invoice'], 10),
                'account.analytic.line': (_get_analytic_line, ['product_uom_id','unit_amount','to_invoice'], 10),
            }),
        'progress': fields.function(_hours_get, method=True, string='Progress (%)', multi='hours', group_operator="avg", help="Computed as: Time Spent / Total Time.",
            store = {
                'project.task': (lambda self, cr, uid, ids, c={}: ids, ['work_ids', 'remaining_hours', 'planned_hours','state'], 10),
                'hr.analytic.timesheet': (_get_task, ['task_id','unit_amount','product_uom_id','to_invoice'], 10),
                'account.analytic.line': (_get_analytic_line, ['product_uom_id','unit_amount','to_invoice'], 10),
            }),
        'delay_hours': fields.function(_hours_get, method=True, string='Delay Hours', multi='hours', help="Computed as difference of the time estimated by the project manager and the real time to close the task.",
            store = {
                'project.task': (lambda self, cr, uid, ids, c={}: ids, ['work_ids', 'remaining_hours', 'planned_hours'], 10),
                'hr.analytic.timesheet': (_get_task, ['task_id','unit_amount','product_uom_id','to_invoice'], 10),
                'account.analytic.line': (_get_analytic_line, ['product_uom_id','unit_amount','to_invoice'], 10),
            }),
        'project_id': fields.many2one('project.project', 'Project', ondelete='cascade', required=True),
    }

task()

####################################################################################
#  Project Task
# ####################################################################################
class project(osv.osv):
    _inherit = "project.project"

    def _get_project_work(self, cr, uid, ids, context=None):
        """Unless the original way of making project - timesheet integration, this time, we can
        have time spent on a task for a certain prjoct, but also time made not in relation with a task
        but directly on the analytical account.
        This trigger should be trigged only when a analytic line is made without task_id."""
        result = {}
        lines = self.pool.get('hr.analytic.timesheet').read(cr, uid, ids, ['id','account_id'], context=context)
        for line in lines:
            if 'account_id' in line and line['account_id']:
                proj_id = self.pool.get('project.project').search(cr, uid, [('analytic_account_id','=',line['account_id'][0])], context=context)[0]
                if proj_id:
                    result[proj_id] = True
        return result.keys()

    def _progress_rate(self, cr, uid, ids, names, arg, context=None):
        """As OpenERP SA made a query for this function field (perf. reason obviously), 
        I must overide it all."""
        res = {}.fromkeys(ids, 0.0)
        progress = {}
        if not ids:
            return res
        cr.execute('''SELECT
                project_id, sum(planned_hours), sum(total_hours), sum(effective_hours), SUM(remaining_hours), SUM(deduced_hours)
            FROM
                project_task
            WHERE
                project_id in %s AND
                state<>'cancelled'
            GROUP BY
                project_id''', (tuple(ids),))
        progress = dict(map(lambda x: (x[0], (x[1],x[2],x[3],x[4],x[5])), cr.fetchall()))
        for project in self.browse(cr, uid, ids, context=context):
            s = progress.get(project.id, (0.0,0.0,0.0,0.0,0.0))
            res[project.id] = {
                'planned_hours': s[0],
                'effective_hours': s[2],
                'total_hours': s[1],
                'progress_rate': s[1] and round(100.0*s[2]/s[1],2) or 0.0,
                'deduced_hours': s[4],
            }
        return res

    def _get_project_task(self, cr, uid, ids, context=None):
        """Not call to super because of:
        
        dev/openerp_c2c/openerp_test_camptocamp/src/server/bin/addons/hr_timesheet_sheet/hr_timesheet_sheet.py", line 291, in write
            return super(hr_timesheet_sheet, self).write(cr, uid, ids, vals, *args, **argv)
          File "/Users/jgrandguillaume/c2c/Code/Customers-dev/openerp_c2c/openerp_test_camptocamp/src/server/bin/osv/orm.py", line 3436, in write
            result += self._columns[field].set(cr, self, id, field, vals[field], user, context=rel_context) or []
          File "/Users/jgrandguillaume/c2c/Code/Customers-dev/openerp_c2c/openerp_test_camptocamp/src/server/bin/osv/fields.py", line 502, in set
            id_new = obj.create(cr, user, act[2], context=context)
          File "/Users/jgrandguillaume/c2c/Code/Customers-dev/openerp_c2c/openerp_test_camptocamp/src/server/bin/addons/hr_timesheet_task/hr_timesheet_task.py", line 166, in create
            context=context)
          File "/Users/jgrandguillaume/c2c/Code/Customers-dev/openerp_c2c/openerp_test_camptocamp/src/server/bin/osv/orm.py", line 3355, in write
            result = self._store_get_values(cr, user, ids, vals.keys(), context) or []
          File "/Users/jgrandguillaume/c2c/Code/Customers-dev/openerp_c2c/openerp_test_camptocamp/src/server/bin/osv/orm.py", line 3736, in _store_get_values
            ids2 = fncts[fnct][2](self, cr, 1, ids, context)
          File "/Users/jgrandguillaume/c2c/Code/Customers-dev/openerp_c2c/openerp_test_camptocamp/src/server/bin/addons/hr_timesheet_task/project.py", line 197, in _get_project_task
            return super(project, self)._get_project_task(cr, uid, ids, context)
        TypeError: super(type, obj): obj must be an instance or subtype of type

        """
        result = {}
        for task in self.pool.get('project.task').browse(cr, uid, ids, context=context):
            if task.project_id: result[task.project_id.id] = True
        return result.keys()
        # return super(project, self)._get_project_task(cr, uid, ids, context)
        
    def _get_analytic_line(self,cr,uid,ids,context=None):
        ts_line_obj = self.pool.get('hr.analytic.timesheet')
        ts_ids = ts_line_obj.search(cr,uid,[('line_id','in',ids)])
        return self.pool.get('project.project')._get_project_work(cr,uid,ts_ids,context)
        
    _columns = {
        'planned_hours': fields.function(_progress_rate, multi="progress", method=True, string='Planned Time', help="Sum of planned hours of all tasks related to this project and its child projects.",
            store = {
                'project.project': (lambda self, cr, uid, ids, c={}: ids, ['tasks'], 20),
                'project.task': (_get_project_task, ['deduced_hours','planned_hours', 'effective_hours', 'remaining_hours', 'total_hours', 'progress', 'delay_hours','state', 'work_ids'], 20),
                'hr.analytic.timesheet': (_get_project_work, ['task_id','unit_amount','product_uom_id','account_id','to_invoice'], 20),
                'account.analytic.line': (_get_analytic_line, ['unit_amount','product_uom_id','account_id','to_invoice'], 20),
            }),
        'effective_hours': fields.function(_progress_rate, multi="progress", method=True, string='Time Spent', help="Sum of spent hours of all tasks related to this project and its child projects.",
            store = {
                'project.project': (lambda self, cr, uid, ids, c={}: ids, ['tasks'], 20),
                'project.task': (_get_project_task, ['deduced_hours','planned_hours', 'effective_hours', 'remaining_hours', 'total_hours', 'progress', 'delay_hours','state', 'work_ids'], 20),
                'hr.analytic.timesheet': (_get_project_work, ['task_id','unit_amount','product_uom_id','account_id','to_invoice'], 20),
                'account.analytic.line': (_get_analytic_line, ['unit_amount','product_uom_id','account_id','to_invoice'], 20),
            }),
        'deduced_hours': fields.function(_progress_rate, multi="progress", method=True, string='Deduced Hours', help="Sum of spent hours with invoice factor of all tasks related to this project and its child projects.",
            store = {
                'project.project': (lambda self, cr, uid, ids, c={}: ids, ['tasks'], 20),
                'project.task': (_get_project_task, ['deduced_hours','planned_hours', 'effective_hours', 'remaining_hours', 'total_hours', 'progress', 'delay_hours','state', 'work_ids'], 20),
                'hr.analytic.timesheet': (_get_project_work, ['task_id','unit_amount','product_uom_id','account_id','to_invoice'], 20),
                'account.analytic.line': (_get_analytic_line, ['unit_amount','product_uom_id','account_id','to_invoice'], 20),
            }),
        'total_hours': fields.function(_progress_rate, multi="progress", method=True, string='Total Time', help="Sum of total hours of all tasks related to this project and its child projects.",
            store = {
                'project.project': (lambda self, cr, uid, ids, c={}: ids, ['tasks'], 20),
                'project.task': (_get_project_task, ['deduced_hours','planned_hours', 'effective_hours', 'remaining_hours', 'total_hours', 'progress', 'delay_hours','state', 'work_ids'], 20),
                'hr.analytic.timesheet': (_get_project_work, ['task_id','unit_amount','product_uom_id','account_id','to_invoice'], 20),
                'account.analytic.line': (_get_analytic_line, ['unit_amount','product_uom_id','account_id','to_invoice'], 20),
            }),
        'progress_rate': fields.function(_progress_rate, multi="progress", method=True, string='Progress', type='float', group_operator="avg", help="Percent of tasks closed according to the total of tasks todo.",
            store = {
                'project.project': (lambda self, cr, uid, ids, c={}: ids, ['tasks'], 20),
                'project.task': (_get_project_task, ['deduced_hours','planned_hours', 'effective_hours', 'remaining_hours', 'total_hours', 'progress', 'delay_hours','state', 'work_ids'], 20),
                'hr.analytic.timesheet': (_get_project_work, ['task_id','unit_amount','product_uom_id','account_id','to_invoice'], 20),
                'account.analytic.line': (_get_analytic_line, ['unit_amount','product_uom_id','account_id','to_invoice'], 20),
            }),
     }
     
project()


class account_analytic_account(osv.osv):

    _inherit = 'account.analytic.account'
    _description = 'Analytic Account'

    _columns = {
        'project_ids': fields.one2many('project.project', 'analytic_account_id', 'Projects'),
    }

account_analytic_account()


class account_analytic_line(osv.osv):
    _inherit = 'account.analytic.line'

    def _amount_currency(self, cr, uid, ids, field_name, arg, context={}):
        return super(account_analytic_line, self)._amount_currency(cr, uid, ids, field_name, arg, context)

    def _get_account_currency(self, cr, uid, ids, field_name, arg, context={}):
        return super(account_analytic_line, self)._get_account_currency(cr, uid, ids, field_name, arg, context)

    def _get_account_line(self, cr, uid, ids, context={}):
        return super(account_analytic_line, self)._get_account_line(cr, uid, ids, context)

    def _get_hr_analytic_timesheet(self, cr, uid, ids, context=None):
        analytic_ts_obj = self.pool.get('hr.analytic.timesheet')
        # search existing analytic timesheet (in case it has been dropped)
        analytic_ts_ids = analytic_ts_obj.\
                          search(cr, uid, [('id', 'in', ids)], context=context)
        aal_ids = [at.line_id.id for at
                   in analytic_ts_obj.\
                      browse(cr, uid, analytic_ts_ids, context=context)]
        return aal_ids

    # we add the trigger on hr.analytic.timesheet in order to compute amount_currency and account_currency when we input an account.analytic.line
    # from a hr.analytic.timesheet
    _columns = {
          'aa_currency_id': fields.function(_get_account_currency, method=True, type='many2one', relation='res.currency', string='Account currency',
                  store={
                      'account.analytic.account': (_get_account_line, ['currency_id','company_id'], 50),
                      'account.analytic.line': (lambda self,cr,uid,ids,c={}: ids, ['amount','unit_amount','product_uom_id'],10),
                      'hr.analytic.timesheet': (_get_hr_analytic_timesheet, ['amount','unit_amount','product_uom_id'], 10)
                  },
                  help="The related analytic account currency."),
          'aa_amount_currency': fields.function(_amount_currency, method=True, digits=(16, int(config['price_accuracy'])), string='Amount currency',
                  store={
                      'account.analytic.account': (_get_account_line, ['currency_id','company_id'], 50),
                      'account.analytic.line': (lambda self,cr,uid,ids,c={}: ids, ['amount','unit_amount','product_uom_id'],10),
                      'hr.analytic.timesheet': (_get_hr_analytic_timesheet, ['amount','unit_amount','product_uom_id'], 10)
                  },
                  help="The amount expressed in the related analytic account currency."),
    }

account_analytic_line()