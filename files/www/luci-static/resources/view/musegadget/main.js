'use strict';
'require view';
'require form';
'require rpc';
'require poll';
'require ui';

var callStatus = rpc.declare({ object: 'musegadget', method: 'status' });
var callCapabilities = rpc.declare({ object: 'musegadget', method: 'capabilities' });
var callLog = rpc.declare({ object: 'musegadget', method: 'log' });
var callImport = rpc.declare({ object: 'musegadget', method: 'import_bundle', params: [ 'bundle' ] });
var callSetToken = rpc.declare({ object: 'musegadget', method: 'set_token', params: [ 'token' ] });
var callUnpair = rpc.declare({ object: 'musegadget', method: 'unpair' });
var callService = rpc.declare({ object: 'musegadget', method: 'service', params: [ 'action' ] });

function badge(ok, yes, no) {
	return E('span', { 'style': 'font-weight:bold;color:' + (ok ? '#2e8b57' : '#c0392b') }, ok ? yes : no);
}

function row(label, value) {
	return E('div', { 'class': 'tr' }, [
		E('div', { 'class': 'td left', 'style': 'width:33%' }, E('strong', {}, label)),
		E('div', { 'class': 'td left' }, value)
	]);
}

function notify(res, okMessage) {
	if (res && res.ok)
		ui.addNotification(null, E('p', {}, okMessage), 'info');
	else
		ui.addNotification(null, E('p', {}, (res && res.error) || _('Request failed')), 'danger');
}

return view.extend({
	load: function() {
		return Promise.all([ callStatus(), callLog(), callCapabilities() ]);
	},

	renderStatus: function(st) {
		var table = E('div', { 'class': 'table' });

		if (!st.installed) {
			table.appendChild(row(_('Installation'), badge(false, '', _('Not installed, run install.sh'))));
			return table;
		}

		table.appendChild(row(_('Service'), badge(st.running, _('Running'), _('Stopped'))));
		table.appendChild(row(_('Dependencies'), badge(st.deps_ok, _('OK'), _('Missing (python3, cryptography or websockets)'))));
		table.appendChild(row(_('Paired with Muse'), badge(st.paired, _('Yes'), _('No, import a pairing bundle below'))));
		table.appendChild(row(_('SDK token'), badge(st.has_token, _('Saved'), _('Not set'))));
		table.appendChild(row(_('Device name'), st.node_id ? st.node_id + ' / ' + st.ble_name : '-'));
		return table;
	},

	render: function(data) {
		var self = this;
		var st = data[0] || {};
		var logText = (data[1] && data[1].log) || '';

		var statusBox = E('div', { 'id': 'musegadget-status' }, this.renderStatus(st));
		var logBox = E('pre', {
			'id': 'musegadget-log',
			'style': 'max-height:20em;overflow:auto;white-space:pre-wrap'
		}, logText || _('No log entries yet.'));

		function button(label, cls, handler) {
			return E('button', { 'class': 'btn cbi-button ' + cls, 'click': ui.createHandlerFn(self, handler) }, label);
		}

		var controls = E('div', { 'class': 'cbi-page-actions', 'style': 'text-align:left' }, [
			button(_('Start'), 'cbi-button-action', function() {
				return callService('start').then(function(r) { notify(r, _('Started')); });
			}), ' ',
			button(_('Restart'), 'cbi-button-action', function() {
				return callService('restart').then(function(r) { notify(r, _('Restarted')); });
			}), ' ',
			button(_('Stop'), 'cbi-button-neutral', function() {
				return callService('stop').then(function(r) { notify(r, _('Stopped')); });
			}), ' ',
			button(_('Unpair'), 'cbi-button-negative', function() {
				if (!confirm(_('Remove the pairing from this router? You will need to pair again to use Muse.')))
					return;
				return callUnpair().then(function(r) { notify(r, _('Pairing removed')); });
			})
		]);

		var bundleArea = E('textarea', {
			'rows': 5,
			'style': 'width:100%;font-family:monospace',
			'placeholder': 'MUSE1:eyJpZGVudGl0eSI6...'
		});
		var importBox = E('div', {}, [
			E('p', {}, _('Pair once on a Linux machine with Bluetooth (see the tutorial in docs/pairing.md), then paste the bundle printed by tools/pair-on-linux.sh here.')),
			bundleArea,
			E('div', { 'class': 'cbi-page-actions', 'style': 'text-align:left' },
				button(_('Import pairing bundle'), 'cbi-button-positive', function() {
					return callImport(bundleArea.value).then(function(r) {
						notify(r, _('Pairing imported. Enable the service below to keep it running.'));
						if (r && r.ok) bundleArea.value = '';
					});
				}))
		]);

		var tokenInput = E('input', { 'type': 'password', 'class': 'cbi-input-password', 'style': 'width:28em', 'placeholder': 'mgst_...' });
		var tokenBox = E('div', {}, [
			E('p', {}, _('The SDK token from gadgets.muse.ai. It is stored only on this router and is not shown again.')),
			tokenInput, ' ',
			button(_('Save token'), 'cbi-button-action', function() {
				return callSetToken(tokenInput.value).then(function(r) {
					notify(r, _('Token saved'));
					if (r && r.ok) tokenInput.value = '';
				});
			})
		]);

		var caps = (data[2] && data[2].capabilities) || [];

		var m = new form.Map('musegadget', _('Muse Gadget'),
			_('Turns this router into a Muse gadget. Muse can then run commands and move files on it as the account chosen below.'));
		var s = m.section(form.NamedSection, 'main', 'musegadget', _('Settings'));
		s.addremove = false;
		var o = s.option(form.Flag, 'enabled', _('Enable'));
		o.rmempty = false;
		o = s.option(form.Value, 'run_as', _('Run commands as'),
			_('Unprivileged account, created automatically if missing. Using root is refused.'));
		o.default = 'muse';
		o.rmempty = false;
		o.validate = function(section_id, value) {
			return (/^[a-z_][a-z0-9_-]{0,30}$/.test(value) && value !== 'root') ? true : _('Enter a valid non-root account name');
		};

		o = s.option(form.Flag, 'allow_shell', _('Allow a shell'),
			_('Keep the SDK\'s generic command that runs any shell command as the account above. Turn off to leave only the capabilities selected below.'));
		o.default = o.enabled;
		o = s.option(form.Flag, 'allow_files', _('Allow file access'),
			_('Keep the SDK\'s generic commands that read and write files as the account above.'));
		o.default = o.enabled;

		var capList = E('ul', { 'style': 'margin:.5em 0 0 1.2em' }, caps.map(function(c) {
			return E('li', {}, [ E('strong', {}, c.title), ' (' + (c.risk === 'action' ? _('changes the router') : _('read-only')) + '): ' + c.summary ]);
		}));
		var cs = m.section(form.NamedSection, 'main', 'musegadget', _('Capabilities offered to Muse'),
			_('Each selected item is advertised to Muse as a command it can call. Items that only read information still send that information to Muse. Items marked * change the router. Changes apply after Save & Apply, when the service restarts and registers again.'));
		cs.addremove = false;
		o = cs.option(form.MultiValue, 'capability', _('Capabilities'));
		o.optional = true;
		caps.forEach(function(c) {
			o.value(c.id, c.title + (c.risk === 'action' ? ' *' : ''));
		});
		if (!caps.length)
			o.description = _('The capability list could not be loaded. Is the service installed?');
		o = cs.option(form.DynamicList, 'control_service', _('Services Muse may control'),
			_('Used by "Control services". Muse can only start, stop or restart the services named here, for example dropbear or openclash.'));
		o.optional = true;

		poll.add(function() {
			return Promise.all([ callStatus(), callLog() ]).then(function(d) {
				var box = document.getElementById('musegadget-status');
				if (box) box.replaceChildren(self.renderStatus(d[0] || {}));
				var log = document.getElementById('musegadget-log');
				if (log) log.textContent = (d[1] && d[1].log) || _('No log entries yet.');
			});
		}, 5);

		return m.render().then(function(mapNode) {
			return E('div', {}, [
				E('h2', {}, _('Muse Gadget')),
				E('div', { 'class': 'cbi-section' }, [ E('h3', {}, _('Status')), statusBox, controls ]),
				E('div', { 'class': 'cbi-section' }, [ E('h3', {}, _('Pairing')), importBox ]),
				E('div', { 'class': 'cbi-section' }, [ E('h3', {}, _('SDK token')), tokenBox ]),
				mapNode,
				E('div', { 'class': 'cbi-section' }, [ E('h3', {}, _('What each capability does')), capList ]),
				E('div', { 'class': 'cbi-section' }, [ E('h3', {}, _('Log')), logBox ])
			]);
		});
	}
});
