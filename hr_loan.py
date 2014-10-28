#!/usr/bin/env python
# vim: set fileencoding=utf-8 :


from datetime import datetime, date
from openerp import netsvc
from openerp.osv import fields, osv
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp

#TODO: automate balance and installment calculation on save
def _employee_get(obj, cr, uid, context=None):
    if context is None:
        context = {}
    ids = obj.pool.get('hr.employee').search(cr, uid, [('user_id', '=', uid)], context=context)
    if ids:
        return ids[0]
    return False

class hr_loan(osv.osv):
    _name = 'hr.loan' 
    _inherit = ['mail.thread', 'ir.needaction_mixin'] 
    _description = 'HR Loan Management' 
    _track = {
        'state': {
          'hr_loan.mt_loan_accepted': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'accepted',
          'hr_loan.mt_loan_refused': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'cancelled',
          'hr_loan.mt_loan_confirmed': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'confirm',
        },
    }
  
    def _balance(self, cr, uid, ids, field_name, args, context=None): 
        res = {} 
        for record in self.browse(cr, uid, ids, context=context): 
            cr.execute('select sum(coalesce(total_amount, 0.0))::float from hr_loan_line where loan_id = %s' % (record.id)) 
            data = filter(None, map(lambda x:x[0], cr.fetchall())) or [0.0] 
            res[record.id] = { 
                'balance' : record.amount + data[0], 
                'paid' : not (record.amount + data[0]) > 0
            } 
        return res 

    def _get_paid_loans(self, cr, uid, ids, context=None):
        res = { this.id : True for this in self.browse(cr, uid, ids, context=context)
                if this.balance = 0 }
        return res.keys()

    _columns = { 
        'name' : fields.char('Name', size=64, select=True, readonly=True), 
        'date' : fields.date('Date', required=True, select=True, readonly=True, states={'draft':[('readonly',False)], 'accepted':[('readonly',False)]}), 
        'employee_id' : fields.many2one('hr.employee', 'Employee', required=True, readonly=True, states={'draft':[('readonly',False)]}), 
        'user_id': fields.many2one('res.users', 'User', required=True),
        'notes' : fields.text('Description', required=True, readonly=True, states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]}),
        'amount' : fields.float('Amount', digits_compute=dp.get_precision('Sale Price'), required=True, readonly=True, states={'draft':[('readonly',False)]]}), 
        'nb_payments': fields.integer("Number of payments"),
        'installment' : fields.float('Due amount per payment', digits_compute=dp.get_precision('Sale Price'), required=True, readonly=True), 
        'balance' : fields.float('Balance', digits_compute=dp.get_precision('Sale Price'), required=True, readonly=True), 
        'date_confirm': fields.date('Confirmation Date', select=True, help="Date of the confirmation of the sheet expense. It's filled when the button Confirm is pressed."),
        'date_valid': fields.date('Validation Date', select=True, help="Date of the acceptation of the sheet expense. It's filled when the button Accept is pressed."),
        'user_valid': fields.many2one('res.users', 'Validation By', readonly=True, states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]}),
        'company_id': fields.many2one('res.company', 'Company', required=True),
        'state': fields.selection([
                ('draft', 'New'),
                ('cancelled', 'Refused'),
                ('confirm', 'Waiting Approval'),
                ('accepted', 'accepted'),
                ('done', 'Waiting Payment'),
                ('paid', 'Paid'),
                ],
                'Status', readonly=True, track_visibility='onchange',
                help='When the loan request is created the status is \'Draft\'.\n It is confirmed by the user and request is sent to admin, the status is \'Waiting Confirmation\'.\
                \nIf the admin accepts it, the status is \'Accepted\'.\n If the accounting entries are made for the loan request, the status is \'Waiting Payment\'.'),
    }

    _defaults = {
        'company_id': lambda s, cr, uid, c: s.pool.get('res.company')._company_default_get(cr, uid, 'hr.employee', context=c),
        'date': fields.date.context_today,
        'state': 'draft',
        'employee_id': _employee_get,
        'user_id': lambda cr, uid, id, c={}: id,
    }

    _sql_constraints = [
        (
              'name_uniq', 
              'unique(name)', 
              'Loan record must be unique !'
        ),
    ]

    def loan_confirm(self, cr, uid, ids, context=None):
        for loan in self.browse(cr, uid, ids):
            if rec.amount <= 0.0: 
            raise osv.except_osv( 
                _('Could not confirm Loan !'), 
                _('Amount must be greater than zero.')) 
            if loan.employee_id and loan.employee_id.parent_id.user_id:
                self.message_subscribe_users(cr, uid, [loan.id], user_ids=[loan.employee_id.parent_id.user_id.id])
        return self.write(cr, uid, ids, {'state': 'confirm', 'date_confirm': time.strftime('%Y-%m-%d')}, context=context)

    def loan_accept(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state': 'accepted', 'date_valid': time.strftime('%Y-%m-%d'), 'user_valid': uid}, context=context)

    def loan_canceled(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state': 'cancelled'}, context=context)

    def condition_paid(self, cr, uid, ids, context=None):
        ok = True
        for l in self.browse(cr, uid, ids, context=context):
            for p in this.project_ids:
                if l.balance > 0:
                    ok = False
        return ok

    def create(self, cr, uid, vals, context=None):
        values = vals 
        if 'employee_id' in vals and vals['employee_id']: 
          employee = self.pool.get('hr.employee').browse(cr, uid, [vals['employee_id']])[0] 
          if vals.get('name','/') == '/':
                vals['name'] = self.pool.get('ir.sequence').get(cr, uid, 'hr.loan') or '/'
        return super(hr_loan, self).create(cr, uid, vals, context=context)
