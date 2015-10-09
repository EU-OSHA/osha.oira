from Acquisition import aq_inner
from euphorie.client import model
from euphorie.client import risk
from euphorie.client.navigation import FindNextQuestion
from euphorie.client.navigation import FindPreviousQuestion
from euphorie.client.navigation import QuestionURL
from euphorie.client.navigation import getTreeData
from euphorie.client.session import SessionManager
from euphorie.client.update import redirectOnSurveyUpdate
from euphorie.client.utils import HasText
from euphorie.content.solution import ISolution
from euphorie.content.utils import StripMarkup
from five import grok
from osha.oira import _
from z3c.saconfig import Session
from zope.component import getMultiAdapter
from zope.i18n import translate
from .interfaces import IOSHAIdentificationPhaseSkinLayer
from .interfaces import IOSHAActionPlanPhaseSkinLayer

grok.templatedir("templates")

IMAGE_CLASS = {
    0: '',
    1: 'twelve',
    2: 'six',
    3: 'four',
    4: 'three',
}

DESCRIPTION_CROP_LENGTH = 200


class OSHAIdentificationView(risk.EvaluationView):
    """ This view is a combination of the Euphorie Identification and Evauation
        views.
        The risk is both identified and evaluated in this step.
    """
    grok.layer(IOSHAIdentificationPhaseSkinLayer)
    grok.template("risk_identification")
    question_filter = None

    def update(self):
        if redirectOnSurveyUpdate(self.request):
            return

        self.risk = self.request.survey.restrictedTraverse(
            self.context.zodb_path.split("/"))

        if self.request.environ["REQUEST_METHOD"] == "POST":
            reply = self.request.form
            answer = reply.get("answer")
            self.context.comment = reply.get("comment")
            self.context.postponed = (answer == "postponed")
            if self.context.postponed:
                self.context.identification = None
            else:
                self.context.identification = answer
                if self.risk.type in ('top5', 'policy'):
                    self.context.priority = 'high'
                elif self.risk.evaluation_method == 'calculated':
                    self.calculatePriority(self.risk, reply)
                elif self.risk.evaluation_method == "direct":
                    self.context.priority = reply.get("priority")

            SessionManager.session.touch()

            if reply["next"] == "previous":
                next = FindPreviousQuestion(
                    self.context,
                    filter=self.question_filter)
                if next is None:
                    # We ran out of questions, step back to intro page
                    url = "%s/identification" % \
                        self.request.survey.absolute_url()
                    self.request.response.redirect(url)
                    return
            else:
                next = FindNextQuestion(
                    self.context,
                    filter=self.question_filter)
                if next is None:
                    # We ran out of questions, proceed to the action plan
                    url = "%s/actionplan" % self.request.survey.absolute_url()
                    self.request.response.redirect(url)
                    return

            url = QuestionURL(self.request.survey, next, phase="identification")
            self.request.response.redirect(url)
        else:
            self.tree = getTreeData(self.request, self.context)
            self.title = self.context.parent.title
            self.show_info = self.risk.image or \
                HasText(self.risk.description) or \
                HasText(self.risk.legal_reference)
            number_images = getattr(self.risk, 'image', None) and 1 or 0
            if number_images:
                for i in range(2, 5):
                    number_images += getattr(
                        self.risk, 'image{0}'.format(i), None) and 1 or 0
            self.has_images = number_images > 0
            self.number_images = number_images
            self.image_class = IMAGE_CLASS[number_images]
            number_files = 0
            for i in range(1, 5):
                number_files += getattr(
                    self.risk, 'file{0}'.format(i), None) and 1 or 0
            self.has_files = number_files > 0
            self.risk_number = self.context.number

            ploneview = getMultiAdapter(
                (self.context, self.request), name="plone")
            stripped_description = StripMarkup(self.risk.description)
            if len(stripped_description) > DESCRIPTION_CROP_LENGTH:
                self.description_intro = ploneview.cropText(
                    stripped_description, DESCRIPTION_CROP_LENGTH)
            else:
                self.description_intro = ""
            self.description_probability = _(
                u"help_default_probability", default=u"Indicate how "
                "likely occurence of this risk is in a normal situation.")
            self.description_frequency = _(
                u"help_default_frequency", default=u"Indicate how often this "
                u"risk occurs in a normal situation.")
            self.description_severity = _(
                u"help_default_severity", default=u"Indicate the "
                "severity if this risk occurs.")
            if getattr(self.request.survey, 'enable_custom_evaluation_descriptions', False):
                if self.request.survey.evaluation_algorithm != 'french':
                    custom_dp = getattr(
                        self.request.survey, 'description_probability', '') or ''
                    self.description_probability = custom_dp.strip() or self.description_probability
                custom_df = getattr(self.request.survey, 'description_frequency', '') or ''
                self.description_frequency = custom_df.strip() or self.description_frequency
                custom_ds = getattr(self.request.survey, 'description_severity', '') or ''
                self.description_severity = custom_ds.strip() or self.description_severity

            super(risk.EvaluationView, self).update()


class OSHAActionPlanView(risk.ActionPlanView):
    grok.layer(IOSHAActionPlanPhaseSkinLayer)
    grok.template("risk_actionplan")

    def update(self):
        if redirectOnSurveyUpdate(self.request):
            return
        context = aq_inner(self.context)

        self.next_is_report = False
        # already compute "next" here, so that we can know in the template
        # if the next step might be the report phase, in which case we
        # need to switch off the sidebar
        next = FindNextQuestion(
            context, filter=self.question_filter)
        if next is None:
            # We ran out of questions, proceed to the report
            url = "%s/report" % self.request.survey.absolute_url()
            self.next_is_report = True
        else:
            url = QuestionURL(
                self.request.survey, next, phase="actionplan")

        if self.request.environ["REQUEST_METHOD"] == "POST":
            reply = self.request.form
            session = Session()
            context.comment = reply.get("comment")
            context.priority = reply.get("priority")

            for plan in context.action_plans:
                session.delete(plan)
            context.action_plans.extend(self.extract_plans_from_request())
            SessionManager.session.touch()

            if reply["next"] == "previous":
                next = FindPreviousQuestion(
                    context, filter=self.question_filter)
                if next is None:
                    # We ran out of questions, step back to intro page
                    url = "%s/evaluation" \
                            % self.request.survey.absolute_url()
                else:
                    url = QuestionURL(
                        self.request.survey, next, phase="actionplan")
            return self.request.response.redirect(url)

        else:
            self.data = context
            if len(context.action_plans) == 0:
                self.data.empty_action_plan = [model.ActionPlan()]

        self.title = context.parent.title
        self.tree = getTreeData(
                self.request, context,
                filter=self.question_filter, phase="actionplan")
        if self.context.is_custom_risk:
            self.risk = self.context
            self.description_intro = u""
            self.risk.description = u""
            number_images = 0
        else:
            self.risk = self.request.survey.restrictedTraverse(
                context.zodb_path.split("/"))
            number_images = getattr(self.risk, 'image', None) and 1 or 0
            if number_images:
                for i in range(2, 5):
                    number_images += getattr(
                        self.risk, 'image{0}'.format(i), None) and 1 or 0
            ploneview = getMultiAdapter(
                (self.context, self.request), name="plone")
            stripped_description = StripMarkup(self.risk.description)
            if len(stripped_description) > DESCRIPTION_CROP_LENGTH:
                self.description_intro = ploneview.cropText(
                    stripped_description, DESCRIPTION_CROP_LENGTH)
            else:
                self.description_intro = ""
            self.solutions = [solution for solution in self.risk.values()
                            if ISolution.providedBy(solution)]

        self.number_images = number_images
        self.has_images = number_images > 0
        self.image_class = IMAGE_CLASS[number_images]
        self.risk_number = self.context.number
        lang = getattr(self.request, 'LANGUAGE', 'en')
        self.delete_confirmation = translate(_(
            u"Are you sure you want to delete this measure? This action can "
            u"not be reverted."),
            target_language=lang)
        self.override_confirmation = translate(_(
            u"The current text in the fields 'Action plan', 'Prevention plan' and "
            u"'Requirements' of this measure will be overwritten. This action cannot be "
            u"reverted. Are you sure you want to continue?"),
            target_language=lang)
        super(risk.ActionPlanView, self).update()

    def extract_plans_from_request(self):
        """ Create new ActionPlan objects by parsing the Request.
        """
        new_plans = []
        form = self.request.form
        form["action_plans"] = []
        for i in range(0, len(form['measure'])):
            measure = dict([p for p in form['measure'][i].items()
                            if p[1].strip()])
            form['action_plans'].append(measure)
            if len(measure):
                budget = measure.get("budget")
                budget = budget and budget.split(',')[0].split('.')[0]
                new_plans.append(
                    model.ActionPlan(
                        action_plan=measure.get("action_plan"),
                        prevention_plan=measure.get("prevention_plan"),
                        requirements=measure.get("requirements"),
                        responsible=measure.get("responsible"),
                        budget=budget,
                        planning_start=measure.get('planning_start'),
                        planning_end=measure.get('planning_end')
                    )
                )
        return new_plans
