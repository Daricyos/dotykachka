"""Module for Dotykacka PoS Config extension."""
__version__ = "1.1"

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    """Extension of pos.config with dotykacka related fields."""

    _inherit = 'pos.config'

    use_dotykacka = fields.Boolean("Process Orders in Dotykacka?", default=False)

    dotykacka_branch_id = fields.Char(string='Dotykacka Branch ID')

    @api.constrains('dotykacka_branch_id')
    def _check_dotykacka_branch_id(self):
        for pos_config in self:
            if not pos_config.dotykacka_branch_id:
                continue
            existing_identifier = self.search(
                [
                    ('id', '!=', pos_config.id),
                    ('dotykacka_branch_id', '=', pos_config.dotykacka_branch_id),
                ],
                limit=1,
            )
            if existing_identifier:
                raise ValidationError(
                    _('Branch %(branch_id)s is already used on register %(pos_name)s.')
                    % {'branch_id': pos_config.dotykacka_branch_id, 'post_name': pos_config.name}
                )
