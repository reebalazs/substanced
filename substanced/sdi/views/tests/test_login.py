import unittest
from pyramid import testing

class Test_logout(unittest.TestCase):
    def setUp(self):
        testing.setUp()

    def tearDown(self):
        testing.tearDown()
        
    def _callFUT(self, request):
        from ..login import logout
        return logout(request)

    def test_it(self):
        request = testing.DummyRequest()
        request.mgmt_path = lambda *arg: '/path'
        response = self._callFUT(request)
        self.assertEqual(response.location, '/path')

class Test_login(unittest.TestCase):
    def setUp(self):
        testing.setUp()

    def tearDown(self):
        testing.tearDown()
        
    def _callFUT(self, context, request):
        from ..login import login
        return login(context, request)

    def test_form_not_submitted(self):
        request = testing.DummyRequest()
        request.mgmt_path = lambda *arg: '/path'
        context = testing.DummyResource()
        result = self._callFUT(context, request)
        self.assertEqual(result['url'], '/path')
        self.assertEqual(result['came_from'], 'http://example.com')
        self.assertEqual(result['login'], '')
        self.assertEqual(result['password'], '')

    def test_form_submitted_csrf_error(self):
        request = testing.DummyRequest()
        request.params['form.submitted'] = True
        request.mgmt_path = lambda *arg: '/path'
        context = testing.DummyResource()
        result = self._callFUT(context, request)
        self.assertEqual(result['url'], '/path')
        self.assertEqual(result['came_from'], 'http://example.com')
        self.assertEqual(result['login'], '')
        self.assertEqual(result['password'], '')
        self.assertEqual(request.session['_f_error'], ['Failed login (CSRF)'])
        
    def test_form_submitted_failed_login_no_user(self):
        from ....testing import make_site
        request = testing.DummyRequest()
        request.params['form.submitted'] = True
        request.params['login'] = 'login'
        request.params['password'] = 'password'
        request.mgmt_path = lambda *arg: '/path'
        request.params['csrf_token'] = request.session.get_csrf_token()
        context = make_site()
        result = self._callFUT(context, request)
        self.assertEqual(result['url'], '/path')
        self.assertEqual(result['came_from'], 'http://example.com')
        self.assertEqual(result['login'], 'login')
        self.assertEqual(result['password'], 'password')
        self.assertEqual(request.session['_f_error'], ['Failed login'])

    def test_form_submitted_failed_login_wrong_password(self):
        from ....testing import make_site
        request = testing.DummyRequest()
        request.params['form.submitted'] = True
        request.params['login'] = 'login'
        request.params['password'] = 'password'
        request.mgmt_path = lambda *arg: '/path'
        request.params['csrf_token'] = request.session.get_csrf_token()
        context = make_site()
        context['principals']['users']['login'] = DummyUser(0)
        context.__services__ = ('principals',)
        result = self._callFUT(context, request)
        self.assertEqual(result['url'], '/path')
        self.assertEqual(result['came_from'], 'http://example.com')
        self.assertEqual(result['login'], 'login')
        self.assertEqual(result['password'], 'password')
        self.assertEqual(request.session['_f_error'], ['Failed login'])

    def test_form_submitted_success(self):
        from ....testing import make_site
        request = testing.DummyRequest()
        request.params['form.submitted'] = True
        request.params['login'] = 'login'
        request.params['password'] = 'password'
        request.mgmt_path = lambda *arg: '/path'
        request.params['csrf_token'] = request.session.get_csrf_token()
        context = make_site()
        user = DummyUser(1)
        user.__oid__ = 1
        context['principals']['users']['login'] = user
        context.__services__ = ('principals',)
        result = self._callFUT(context, request)
        self.assertEqual(result.location, 'http://example.com')
        self.assertTrue(result.headers)

class DummyUser(object):
    def __init__(self, result):
        self.result = result

    def check_password(self, password):
        return self.result

