from Acquisition import aq_inner
from Products.statusmessages.interfaces import IStatusMessage
from euphorie.client import model
from euphorie.client import module
from euphorie.client.navigation import FindNextQuestion
from euphorie.client.navigation import FindPreviousQuestion
from euphorie.client.navigation import QuestionURL
from euphorie.client.navigation import getTreeData
from euphorie.client.session import SessionManager
from euphorie.client.update import redirectOnSurveyUpdate
from euphorie.content import MessageFactory as _
from euphorie.content.interfaces import ICustomRisksModule
from euphorie.content.profilequestion import IProfileQuestion
from five import grok
from osha.oira.client import interfaces
from sqlalchemy import sql
from z3c.saconfig import Session

grok.templatedir("templates")


class Mixin(object):

    def _update(self, superclass):
        if redirectOnSurveyUpdate(self.request):
            return

        if self.request.environ["REQUEST_METHOD"] == "POST":
            return super(superclass, self).update()

        context = aq_inner(self.context)
        module = self.request.survey.restrictedTraverse(
                                self.context.zodb_path.split("/"))

        if IProfileQuestion.providedBy(module) and context.depth == 2:
            next = FindNextQuestion(context, filter=self.question_filter)
            if next is None:
                if self.phase == 'identification':
                    url = "%s/evaluation" % self.request.survey.absolute_url()
                elif self.phase == 'evaluation':
                    url = "%s/actionplan" % \
                            self.request.survey.absolute_url()
                elif self.phase == 'actionplan':
                    url = "%s/report" % self.request.survey.absolute_url()
            else:
                url = QuestionURL(self.request.survey, next, phase=self.phase)
            return self.request.response.redirect(url)
        else:
            return super(superclass, self).update()


    def get_custom_risks(self):
        session = SessionManager.session
        query = Session.query(model.Risk).filter(
            sql.and_(
                model.Risk.is_custom_risk == True,
                model.Risk.path.startswith(model.Module.path),
                model.Risk.session_id == session.id
            )
        )
        return query.all()


class CustomizationView(module.CustomizationView, Mixin):
    grok.context(model.Module)
    grok.require("euphorie.client.ViewSurvey")
    grok.layer(interfaces.IOSHACustomizationPhaseSkinLayer)
    grok.template("module_customization")

    def update(self):
        if redirectOnSurveyUpdate(self.request):
            return

        context = aq_inner(self.context)
        survey = self.request.survey
        self.module = survey.restrictedTraverse(self.context.zodb_path.split("/"))
        self.title = self.context.title
        self.tree = getTreeData(
                self.request, self.context, phase="identification",
                filter=model.NO_CUSTOM_RISKS_FILTER)

        if self.request.environ["REQUEST_METHOD"] == "POST":
            reply = self.request.form
            if reply.get("next") == "previous":
                url = "%s/identification/%d" % (
                        self.request.survey.absolute_url(),
                        int(self.context.path))
                return self.request.response.redirect(url)

            elif reply.get("next") == "next":
                self.add_custom_risks(reply)
                url = "%s/actionplan" % self.request.survey.absolute_url()
                return self.request.response.redirect(url)

        return super(CustomizationView, self).update()

    def add_custom_risks(self, form):
        session = SessionManager.session
        self.context.removeChildren() # Clear previous custom risks
        for risk_values in form.get('risk', []):
            if not risk_values.get("description") or not risk_values.get("priority"):
                IStatusMessage(self.request).add(
                        _(u"Please fill in the required fields"),
                        type="error")
                self.request.set('errors', {
                    'description': not risk_values.get("description"),
                    'priority': not risk_values.get("priority"),
                });
                return;
            risk = model.Risk(
                comment=risk_values.get('comment'),
                priority=risk_values['priority'],
                risk_id=None,
                risk_type='risk', # XXX Could it also be top5 or policy?
                skip_evaluation=True,
                title=risk_values['description'],
                identification="no"
            )
            risk.is_custom_risk = True
            risk.skip_children = False
            risk.postponed = False
            risk.has_description = None
            risk.zodb_path = "/".join([session.zodb_path] + [self.context.zodb_path] + ['1'])
            risk.profile_index = 0 # XXX: not sure what this is for
            self.context.addChild(risk)
            IStatusMessage(self.request).add(
                    _(u"Your custom risk has been succesfully created."),
                    type="success")


class IdentificationView(module.IdentificationView, Mixin):
    grok.layer(interfaces.IOSHAIdentificationPhaseSkinLayer)
    grok.template("module_identification")


    def update(self):
        if redirectOnSurveyUpdate(self.request):
            return
        context = aq_inner(self.context)
        module = self.request.survey.restrictedTraverse(
                                        context.zodb_path.split("/"))
        if self.request.environ["REQUEST_METHOD"] == "POST":
            self.save_and_continue(module)
        else:
            if ICustomRisksModule.providedBy(module) \
                    and not self.context.skip_children \
                    and len(self.get_custom_risks()):
                url = "%s/customization/%d" % (
                    self.request.survey.absolute_url(),
                    int(self.context.path))
                return self.request.response.redirect(url)

            self.tree = getTreeData(self.request, context,
                    filter=model.NO_CUSTOM_RISKS_FILTER)
            self.title = context.title
            self.module = module
            super(IdentificationView, self).update()


    def save_and_continue(self, module):
        """ We received a POST request.
            Submit the form and figure out where to go next.
        """
        context = aq_inner(self.context)
        reply = self.request.form
        if module.optional:
            if "skip_children" in reply:
                context.skip_children = reply.get("skip_children")
                context.postponed = False
            else:
                context.postponed = True
            SessionManager.session.touch()

        if reply["next"] == "previous":
            next = FindPreviousQuestion(context,
                    filter=self.question_filter)
            if next is None:
                # We ran out of questions, step back to intro page
                url = "%s/identification" % \
                        self.request.survey.absolute_url()
                self.request.response.redirect(url)
                return
        else:
            if ICustomRisksModule.providedBy(module):
                if not context.skip_children:
                    # The user will now be allowed to create custom
                    # (user-defined) risks.
                    url = "%s/customization/%d" % (
                            self.request.survey.absolute_url(),
                            int(self.context.path))
                    return self.request.response.redirect(url)
                else:
                    # We ran out of questions, proceed to the evaluation
                    url = "%s/actionplan" % self.request.survey.absolute_url()
                    return self.request.response.redirect(url)
            next = FindNextQuestion(context, filter=self.question_filter)
            if next is None:
                # We ran out of questions, proceed to the evaluation
                url = "%s/evaluation" % self.request.survey.absolute_url()
                return self.request.response.redirect(url)

        url = QuestionURL(self.request.survey, next,
                phase="identification")
        self.request.response.redirect(url)


class EvaluationView(module.EvaluationView, Mixin):
    grok.layer(interfaces.IOSHAEvaluationPhaseSkinLayer)
    grok.template("module_evaluation")

    def update(self):
        return self._update(EvaluationView)


class ActionPlanView(module.ActionPlanView, Mixin):
    grok.layer(interfaces.IOSHAActionPlanPhaseSkinLayer)
    grok.template("module_actionplan")

    def update(self):
        return self._update(ActionPlanView)
