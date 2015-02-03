from werkzeug.exceptions import Unauthorized
import mock
from flask import request
from . import test_utils
from ..views.bbauth import handle_auth_error
from ...exceptions import AuthenticationException
from ...models.plots import Plot
from ..models.user import User, new_user
from ..models.docs import Doc
from ..serverbb import BokehServerTransaction
from ..app import app, bokeh_app
from ..views.main import _makedoc
class AuthTestCase(test_utils.FlaskClientTestCase):
    options = {'multi_user' : True}
    def test_handle_auth_error_decorator(self):
        @handle_auth_error
        def helper1():
            return 'foo'
        @handle_auth_error
        def helper2():
            raise AuthenticationException('bad!')
        assert helper1() == 'foo'
        self.assertRaises(Unauthorized, helper2)

    def test_write_auth_checks_rw_users_field(self):
        user = User('test1', 'sdfsdf', 'sdfsdf')
        user2 = User('test2', 'sdfsdf', 'sdfsdf')
        doc = Doc('docid', 'title', ['test1'], [], None,
                  None, None, False)
        with app.test_request_context("/"):
            BokehServerTransaction(user, doc, 'rw')
        with app.test_request_context("/"):
            self.assertRaises(AuthenticationException, BokehServerTransaction,
                              user2, doc, 'rw')

    def test_write_auth_ignores_r_users_field(self):
        user2 = User('test2', 'sdfsdf', 'sdfsdf')
        doc = Doc('docid', 'title', ['test1'], ['test'], None,
                  None, None, False)
        with app.test_request_context("/"):
            self.assertRaises(AuthenticationException, BokehServerTransaction,
                              user2, doc, 'rw')

    def test_read_auth_checks_both_fields(self):
        user2 = User('test2', 'sdfsdf', 'sdfsdf')
        user = User('test1', 'sdfsdf', 'sdfsdf')
        doc = Doc('docid', 'title', ['test1'], ['test2'], None,
                  None, None, False)
        with app.test_request_context("/"):
            BokehServerTransaction(user, doc, 'r')
        with app.test_request_context("/"):
            BokehServerTransaction(user2, doc, 'r')

    def test_permissions_with_temporary_docid(self):
        user2 = User('test2', 'sdfsdf', 'sdfsdf')
        user = User('test1', 'sdfsdf', 'sdfsdf')
        doc = Doc('docid', 'title', [], ['test2'], None,
                  None, None, False)
        # with temporary docid, a user must be able to read in order to get write access
        # this call should fail
        with app.test_request_context("/"):
            self.assertRaises(AuthenticationException, BokehServerTransaction,
                              user, doc, 'rw', temporary_docid="foobar")

class TransactionManagerTestCase(test_utils.FlaskClientTestCase):
    options = {'multi_user' : True}
    def setUp(self):
        super(TransactionManagerTestCase, self).setUp()
        self.user = new_user(bokeh_app.servermodel_storage, "test1",
                        "password")
        self.server_docobj = _makedoc(
            bokeh_app.servermodel_storage, self.user, 'testdoc1'
        )
        #create 2 views
        original_doc = bokeh_app.backbone_storage.get_document(self.server_docobj.docid)
        plot1 = Plot(title='plot1')
        original_doc.add(plot1)
        bokeh_app.backbone_storage.store_document(original_doc)

    def transaction(self, temporary_docid, mode='rw'):
        context = BokehServerTransaction(
            self.user,
            self.server_docobj,
            mode,
            temporary_docid=temporary_docid)
        return context

    def test_base_object_exists_in_cow_context(self):
        with app.test_request_context("/"):
            with self.transaction('test1') as t:
                assert t.clientdoc.context.children[0].title == 'plot1'

    def test_writing_in_cow_context_persists(self):
        with app.test_request_context("/"):
            with self.transaction('test1') as t:
                t.clientdoc.add(Plot(title='plot2'))
            with self.transaction('test1') as t:
                assert len(t.clientdoc.context.children) == 2
                assert t.clientdoc.context.children[1].title == 'plot2'

    def test_writing_in_cow_context_does_not_modify_original(self):
        with app.test_request_context("/"):
            with self.transaction('test1') as t:
                t.clientdoc.add(Plot(title='plot2'))
            with self.transaction(None) as t:
                assert len(t.clientdoc.context.children) == 1
            with self.transaction('test1') as t:
                assert len(t.clientdoc.context.children) == 2

    def test_read_only_context_does_not_write(self):
        with app.test_request_context("/"):
            with self.transaction(None, mode='r') as t:
                t.clientdoc.add(Plot(title='plot2'))
            with self.transaction(None, mode='r') as t:
                assert len(t.clientdoc.context.children) == 1
