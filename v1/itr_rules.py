# v1/itr_rules.py
"""ATO-aware account-name matching and ITR labelling logic.

This module maps Xero/accounting report rows to conservative Company Tax Return
labels for review workpapers. It is intentionally rule-based and review-first:
- Item 6 labels are accounting P&L presentation labels.
- Item 7 labels are tax reconciliation labels and should normally be reviewed.
- Item 8 labels are financial/other information or balance-sheet support labels.

Keep static return metadata, tax rates, thresholds, worksheet templates and output
layout outside this file, for example in itr_metadata.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal

ReportType = Literal["profit_and_loss", "balance_sheet", "trial_balance", "general_ledger", "unknown"]
Treatment = Literal["financial_label_only", "review_only", "support_only", "unmapped"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class LabelRule:
    patterns: tuple[str, ...]
    itr_ref: str
    itr_label: str
    treatment: Treatment
    confidence: Confidence
    review_note: str
    reason: str
    recon_itr_ref: str = ""

    def as_mapping(self) -> dict[str, str]:
        return {
            "ITR Ref": self.itr_ref,
            "ITR Label": self.itr_label,
            "Treatment": self.treatment,
            "Confidence": self.confidence,
            "Review Note": self.review_note,
            "Label Reason": self.reason,
            "Recon ITR Ref": self.recon_itr_ref,
        }


def R(
    patterns: Iterable[str],
    itr_ref: str,
    itr_label: str,
    treatment: Treatment,
    confidence: Confidence,
    review_note: str,
    reason: str,
    recon_itr_ref: str = "",
) -> LabelRule:
    return LabelRule(tuple(patterns), itr_ref, itr_label, treatment, confidence, review_note, reason, recon_itr_ref)


# ---------------------------------------------------------------------------
# A. Profit and loss rules
# ---------------------------------------------------------------------------
# ATO notes built into the mapping:
# - Item 6 is accounting income/expense presentation.
# - Item 7 is tax reconciliation. Use review_only for tax-sensitive adjustments.
# - Wages/salaries are not Item 6D. Item 6D is superannuation expense.
#   Wages usually sit at 6S and also support Item 8D total salary/wage expenses.
# - Domestic/overseas split cannot be reliably inferred from account name alone,
#   so interest, lease and royalty accounts are review_only where source matters.

PL_RULES: list[LabelRule] = [
    # ------------------------------------------------------------------
    # A. Expense rules that must be tested BEFORE income/sales rules
    # ------------------------------------------------------------------

    R(
        [
            r"\bcogs\b",
            r"\bcost of sales\b",
            r"\bcost of goods sold\b",
            r"\bpurchases?\b",
            r"\bdirect materials?\b",
            r"\bdirect labo(u)?r\b",
            r"\bpackaging\b",
            r"\bfreight in\b",
            r"\binbound freight\b",
            r"\bimport freight\b",
            r"\bcustoms duty\b",
            r"\bimport duty\b",
            r"\blanded cost\b",
        ],
        "Exp - 6A",
        "Cost of sales",
        "financial_label_only",
        "high",
        "Review stock treatment if material.",
        "Mapped cost of sales/direct cost to Item 6 expense label A.",
    ),

    # Consultants / contractors / agency fees / commissions.
    # This catches:
    # - Consultants - Australia
    # - Consultants - USA
    # - Consultants - Europe
    # - Consultants - Asia
    # - R & D Consultants
    # - Advertising Agency
    # - Agency Retainer
    # - Media commission
    # - SEO Services
    # - Agency CRO Services
    # - Athlete Affiliate Sale Commissions
    R(
        [
            r"\bconsultants?\b",
            r"\bconsulting fee\b",
            r"\bconsultant fee\b",
            r"\bcontractor\b",
            r"\bcontractors\b",
            r"\bsubcontractor\b",
            r"\bsub contractor\b",
            r"\blabour hire\b",
            r"\blabor hire\b",
            r"\bagency fee\b",
            r"\bagency retainer\b",
            r"\badvertising agency\b",
            r"\bmarketing agency\b",
            r"\bmanagement fee\b",
            r"\bservice fee\b",
            r"\bservice fees\b",
            r"\bseo services?\b",
            r"\bcro services?\b",
            r"\bagency .* services?\b",
            r"\bcommission expense\b",
            r"\bcommissions paid\b",
            r"\bmedia commission\b",
            r"\bsales commission expense\b",
            r"\baffiliate .* commissions?\b",
            r"\baffiliate sale commissions?\b",
            r"\bathlete affiliate sale commissions?\b",
        ],
        "Exp - 6C",
        "Contractor, sub-contractor and commission expenses",
        "review_only",
        "medium",
        "Confirm this is not salaries/wages and not already included in cost of sales.",
        "Mapped contractor/consultant/agency/commission account to Item 6 expense label C.",
    ),

    # ------------------------------------------------------------------
    # B. Income labels
    # ------------------------------------------------------------------

    R(
        [
            r"\babn not quoted\b",
            r"\bno abn\b",
            r"\bwithholding.*abn\b",
        ],
        "Inc - 6A",
        "Gross payments where ABN not quoted",
        "review_only",
        "medium",
        "Only use if gross payments were subject to withholding because ABN was not quoted.",
        "Account name suggests Item 6 income label A.",
    ),

    R(
        [
            r"\bforeign resident withholding\b",
            r"\bfrw\b",
        ],
        "Inc - 6B",
        "Gross payments subject to foreign resident withholding",
        "review_only",
        "medium",
        "Only complete for relevant foreign resident withholding income.",
        "Account name suggests Item 6 income label B.",
    ),

    # Main sales / trading / service income rule.
    # This is deliberately broad and catches xxx Sales after normalisation:
    # - Sales
    # - Yachting Sales
    # - Dinghy Sales
    # - Paddle Sales
    # - Elements Sales
    # - Club Sales
    # - Miscellaneous Sales
    # - Cash Discount
    # - Rebates Given
    # - Web Discount
    # - Warranty Revenue
    R(
        [
            r"(^|\s)sales?($|\s)",
            r"\b\w+\s+sales?\b",
            r"\b.+\s+sales?\b",
            r"\bsales revenue\b",
            r"\bsales income\b",
            r"\btrading income\b",
            r"\bbusiness income\b",
            r"\boperating revenue\b",
            r"\bservice revenue\b",
            r"\brevenue\b",
            r"\bfreight income\b",
            r"\bshipping income\b",
            r"\bcustomi[sz]ation\b",
            r"\bcustomi[sz]ation income\b",
            r"\blicence fee\b",
            r"\blicense fee\b",
            r"\bweb licence fee\b",
            r"\bweb license fee\b",
            r"\blicence income\b",
            r"\blicense income\b",
            r"\brestocking fee\b",
            r"\bwarranty revenue\b",
            r"\bwarranty income\b",
            r"\bclub sales\b",
            r"\bclub shop fulfilment\b",
            r"\bpos\b",
            r"\bpoint of sale\b",
            r"\bcommission income\b",
            r"\blicensee commission\b",
            r"\bsponsorship income\b",
            r"\bsponsorship revenue\b",
            r"\bsponsorship\b",
            r"\bcash discount\b",
            r"\bsales discount\b",
            r"\bweb discount\b",
            r"\bdiscount allowed\b",
            r"\bdiscount given\b",
            r"\brebates? given\b",
            r"\bsales rebate\b",
        ],
        "Inc - 6C",
        "Other sales of goods and services",
        "financial_label_only",
        "high",
        "Gross income should be shown before set-off/netting and generally GST-exclusive where GST applies.",
        "Mapped ordinary sales/service/trading income to Item 6 income label C.",
    ),

    R(
        [
            r"\bpartnership distribution\b",
            r"\bpartnership income\b",
            r"\bshare of partnership\b",
        ],
        "Inc - 6D",
        "Gross distribution from partnerships",
        "review_only",
        "medium",
        "Check partnership statement, gross-up/franking credits and any Item 7 adjustments.",
        "Account name suggests partnership distribution income.",
    ),

    R(
        [
            r"\btrust distribution\b",
            r"\btrust income\b",
            r"\bunit trust distribution\b",
            r"\bmanaged fund distribution\b",
        ],
        "Inc - 6E",
        "Gross distribution from trusts",
        "review_only",
        "medium",
        "Check trust income schedule, gross-up/franking credits and capital gain components.",
        "Account name suggests trust distribution income.",
    ),

    R(
        [
            r"\binterest income\b",
            r"\binterest received\b",
            r"\bbank interest\b",
            r"\bloan interest income\b",
        ],
        "Inc - 6F",
        "Gross interest",
        "financial_label_only",
        "high",
        "",
        "Mapped interest income to Item 6F.",
    ),

    R(
        [
            r"\brental income\b",
            r"\brent received\b",
            r"\blease income\b",
            r"\bhire income\b",
        ],
        "Inc - 6G",
        "Gross rent and other leasing and hiring income",
        "financial_label_only",
        "medium",
        "Check whether this is rental/leasing income or ordinary trading income.",
        "Mapped rental/leasing/hiring income to Item 6G.",
    ),

    R(
        [
            r"\bdividend income\b",
            r"\bdividends? received\b",
            r"\bfranked dividend\b",
            r"\bunfranked dividend\b",
            r"\bnon share dividend\b",
            r"\bnon-share dividend\b",
        ],
        "Inc - 6H",
        "Total dividends",
        "review_only",
        "medium",
        "Do not include franking credits at 6H. Franking credits may need Item 7J or 7C review.",
        "Mapped dividend income to Item 6H review.",
    ),

    R(
        [
            r"\bfringe benefit employee contribution\b",
            r"\bfbt employee contribution\b",
            r"\bemployee contribution.*fringe\b",
        ],
        "Inc - 6I",
        "Fringe benefit employee contributions",
        "review_only",
        "medium",
        "Confirm this is an employee contribution for fringe benefits.",
        "Mapped FBT employee contribution income to Item 6I.",
    ),

    R(
        [
            r"\bunrealised gain\b",
            r"\bunrealized gain\b",
            r"\bfair value gain\b",
            r"\brevaluation gain\b",
        ],
        "Inc - 6J",
        "Unrealised gains on revaluation of assets to fair value",
        "review_only",
        "medium",
        "If not assessable, subtract at Item 7Q. If capital, consider Item 7A net capital gain.",
        "Mapped unrealised/fair-value gain to Item 6J and Item 7 review.",
        "7Q",
    ),

    R(
        [
            r"\bgovernment grant\b",
            r"\bgovernment payment\b",
            r"\bindustry payment\b",
            r"\bsubsidy\b",
            r"\bfuel tax credit\b",
            r"\bproducer rebate\b",
            r"\bapprentice.*subsidy\b",
            r"\bwage subsidy\b",
        ],
        "Inc - 6Q",
        "Assessable government industry payments",
        "review_only",
        "medium",
        "Review assessability. Some grants/payments may be non-assessable and need Item 7Q instead.",
        "Mapped government payment/grant style income to Item 6Q review.",
    ),

    # 6R should be TRUE other gross income, not ordinary sales/service revenue.
    # Examples:
    # - insurance recovery
    # - bad debt recovery
    # - gains on disposal
    # - royalty income
    # - miscellaneous non-trading income
    # Do NOT send ordinary xxx Sales / POS / warranty / restocking / web licence here.
    R(
        [
            r"\bgain.*disposal\b",
            r"\bprofit.*disposal\b",
            r"\bgain.*sale.*asset\b",
            r"\bprofit.*sale.*asset\b",
            r"\binsurance recover(y|ies)\b",
            r"\bbad debt recover(y|ies)\b",
            r"\brecovery income\b",
            r"\broyalty income\b",
            r"\bother income\b",
            r"\bmiscellaneous income\b",
            r"\bmisc income\b",
            r"\bnon government subsidy\b",
            r"\blate charges?\b",
        ],
        "Inc - 6R",
        "Other gross income",
        "review_only",
        "medium",
        "Review assessability and whether a more specific Item 6 label applies.",
        "Mapped other/gain/recovery income to Item 6R.",
    ),

    # ------------------------------------------------------------------
    # C. Tax-sensitive expenses
    # Keep Item 6 label in ITR Ref.
    # Put Item 7 adjustment in Recon ITR Ref.
    # ------------------------------------------------------------------

    R(
        [
            r"\bincome tax expense\b",
            r"\bcompany tax\b",
            r"\bcurrent tax expense\b",
            r"\btax provision\b",
        ],
        "Exp - 6S",
        "All other expenses - income tax expense review",
        "review_only",
        "high",
        "Confirm this is company income tax, not GST/PAYG. Usually add back at Item 7W if included in accounts.",
        "Mapped income tax expense to Item 6S and flagged Item 7W review.",
        "7W",
    ),

    R(
        [
            r"\bdeferred tax\b",
            r"\bdeferred income tax\b",
            r"\bdeferred tax expense\b",
            r"\bdeferred tax benefit\b",
        ],
        "Exp - 6S",
        "All other expenses - deferred tax review",
        "review_only",
        "medium",
        "Remove accounting deferred tax effect from taxable income calculation as needed.",
        "Mapped deferred tax to Item 6S and Item 7W review.",
        "7W",
    ),

    R(
        [
            r"\br and d\b",
            r"\br&d\b",
            r"\bresearch and development\b",
            r"\bresearch development\b",
        ],
        "Exp - 6C",
        "Contractor, sub-contractor and commission expenses - R&D consultant review",
        "review_only",
        "medium",
        "Check R&D schedule. If subject to R&D tax incentive, add back at Item 7D.",
        "Mapped R&D consultant/expenditure to Item 6C and flagged Item 7D review.",
        "7D",
    ),

    R(
        [
            r"\bfines?\b",
            r"\bpenalt(y|ies)\b",
            r"\binfringement\b",
            r"\bspeeding fine\b",
            r"\bparking fine\b",
        ],
        "Exp - 6S",
        "All other expenses - fines and penalties review",
        "review_only",
        "high",
        "Review and add back if non-deductible.",
        "Mapped fines/penalties to Item 6S and flagged Item 7W review.",
        "7W",
    ),

    R(
        [
            r"\bentertainment\b",
            r"\bmeals? entertainment\b",
            r"\bstaff function\b",
            r"\bclient entertainment\b",
        ],
        "Exp - 6S",
        "All other expenses - entertainment review",
        "review_only",
        "medium",
        "Review FBT and deductibility before adding back.",
        "Mapped entertainment-style expense to Item 6S and flagged Item 7W review.",
        "7W",
    ),

    R(
        [
            r"\bdonation\b",
            r"\bdonations\b",
            r"\bgift\b",
            r"\bgifts\b",
            r"\bcharity\b",
            r"\bsponsorship donation\b",
        ],
        "Exp - 6S",
        "All other expenses - gifts/donations review",
        "review_only",
        "medium",
        "Check DGR status. Add back non-deductible portion at Item 7W or claim extra deductible amount at Item 7X if applicable.",
        "Mapped gifts/donations to Item 6S and tax reconciliation review.",
        "7W",
    ),

    R(
        [
            r"\bprepaid\b",
            r"\bprepayment\b",
            r"\bprepaid expense\b",
        ],
        "Exp - 6S",
        "All other expenses - prepayment review",
        "review_only",
        "medium",
        "Check prepayment timing rules; adjustment may be Item 7W or Item 7X.",
        "Mapped prepaid expense to Item 6S and Item 7 timing review.",
        "7W",
    ),

    R(
        [
            r"\bcapital expense\b",
            r"\bcapitalised\b",
            r"\bcapitalized\b",
            r"\bestablishment cost\b",
            r"\bacquisition cost\b",
            r"\bblack ?hole\b",
            r"\bsection 40 ?880\b",
            r"\bs40 ?880\b",
        ],
        "Exp - 6S",
        "All other expenses - capital expenditure review",
        "review_only",
        "medium",
        "If expensed in accounts, add back non-deductible amount at 7W and consider allowable deduction at 7Z or 7X.",
        "Mapped capital/project expenditure to Item 6S and Item 7 review.",
        "7W",
    ),

    # ------------------------------------------------------------------
    # D. Normal expense labels
    # ------------------------------------------------------------------

    R(
        [
            r"\bsuperannuation\b",
            r"\bsuper guarantee\b",
            r"\bsgc\b",
            r"\bemployer super\b",
            r"\bsuper expense\b",
        ],
        "Exp - 6D",
        "Superannuation expenses",
        "review_only",
        "medium",
        "Deduction is usually based on contributions made; check unpaid/non-complying/SGC amounts.",
        "Mapped superannuation expense to Item 6D.",
    ),

    R(
        [
            r"\bdoubtful debt\b",
            r"\bprovision for doubtful debts\b",
            r"\bimpairment.*receivable\b",
        ],
        "Exp - 6S",
        "All other expenses - doubtful debt provision review",
        "review_only",
        "medium",
        "Doubtful debt provisions should not be included at 6E; add back at Item 7W if not deductible.",
        "Mapped doubtful debt/provision to 6S and 7W review.",
        "7W",
    ),

    R(
        [
            r"\bbad debts?\b",
            r"\bbad debt written off\b",
            r"\bdebt written off\b",
        ],
        "Exp - 6E",
        "Bad debts",
        "review_only",
        "medium",
        "Specific bad debts may be deductible; doubtful debt provisions should usually be 6S and add-back review.",
        "Mapped bad debt write-off to Item 6E review.",
    ),

    R(
        [
            r"\boverseas lease\b",
            r"\bforeign lease\b",
            r"\bnon resident lease\b",
            r"\bnon-resident lease\b",
        ],
        "Exp - 6I",
        "Lease expenses overseas",
        "review_only",
        "medium",
        "Confirm overseas/non-resident lease and withholding obligations.",
        "Mapped overseas lease expense to Item 6I.",
    ),

    R(
        [
            r"\blease expense\b",
            r"\bequipment lease\b",
            r"\bplant lease\b",
            r"\bvehicle lease\b",
            r"\bfinance lease\b",
            r"\boperating lease\b",
        ],
        "Exp - 6F",
        "Lease expenses within Australia",
        "review_only",
        "medium",
        "Assumed Australian lease unless account suggests overseas. Check whether land/building rent should be 6H.",
        "Mapped lease expense to Item 6F review.",
    ),

    R(
        [
            r"\brent\b",
            r"\brental expense\b",
            r"\bpremises rent\b",
            r"\boffice rent\b",
            r"\bwarehouse rent\b",
            r"\bland rent\b",
            r"\bproperty rent\b",
        ],
        "Exp - 6H",
        "Rent expenses",
        "financial_label_only",
        "medium",
        "Use for tenant rental of land/buildings. Private/capital components need review.",
        "Mapped rent account to Item 6H.",
    ),

    R(
        [
            r"\boverseas interest\b",
            r"\bforeign interest expense\b",
            r"\bnon resident interest\b",
            r"\bnon-resident interest\b",
        ],
        "Exp - 6J",
        "Interest expenses overseas",
        "review_only",
        "medium",
        "Check withholding tax, international dealings schedule and thin capitalisation/debt deduction limits.",
        "Mapped overseas interest expense to Item 6J review.",
    ),

    R(
        [
            r"\binterest expense\b",
            r"\binterest paid\b",
            r"\bloan interest\b",
            r"\bbank interest expense\b",
            r"\bfinance interest\b",
        ],
        "Exp - 6V",
        "Interest expenses within Australia",
        "review_only",
        "medium",
        "Assumed domestic unless account suggests overseas. Check thin capitalisation/debt deduction limits and private/non-deductible components.",
        "Mapped interest expense to Item 6V review.",
    ),

    R(
        [
            r"\boverseas royalty\b",
            r"\bforeign royalty\b",
            r"\bnon resident royalty\b",
            r"\bnon-resident royalty\b",
        ],
        "Exp - 6U",
        "Royalty expenses overseas",
        "review_only",
        "medium",
        "Check withholding tax, international dealings schedule and royalty classification.",
        "Mapped overseas royalty expense to Item 6U review.",
    ),

    R(
        [
            r"\broyalty\b",
            r"\broyalties\b",
            r"\broylaties\b",
            r"\blicence royalty\b",
            r"\blicense royalty\b",
        ],
        "Exp - 6W",
        "Royalty expenses within Australia",
        "review_only",
        "medium",
        "Assumed domestic unless account suggests overseas. Check royalty classification and withholding if applicable.",
        "Mapped royalty expense to Item 6W review.",
    ),

    R(
        [
            r"\bdepreciation\b",
            r"\bamortisation\b",
            r"\bamortization\b",
            r"\bdepn\b",
        ],
        "Exp - 6X",
        "Depreciation expenses",
        "review_only",
        "medium",
        "For non-SBE simplified depreciation, book depreciation generally needs Item 7W add-back and tax decline-in-value deduction at Item 7F.",
        "Mapped depreciation/amortisation to Item 6X and Item 7 review.",
        "7W",
    ),

    R(
        [
            r"\bmotor vehicle\b",
            r"\bvehicle running\b",
            r"\bfuel\b",
            r"\bregistration\b",
            r"\brego\b",
            r"\bparking\b",
            r"\btoll\b",
            r"\bcar expense\b",
            r"\btruck expense\b",
            r"\bvehicle insurance\b",
        ],
        "Exp - 6Y",
        "Motor vehicle expenses",
        "review_only",
        "medium",
        "6Y is for running expenses only; do not include lease, interest or depreciation components here.",
        "Mapped motor vehicle running costs to Item 6Y.",
    ),

    R(
        [
            r"\brepairs?\b",
            r"\bmaintenance\b",
            r"\bservicing\b",
            r"\bplant maintenance\b",
            r"\bequipment maintenance\b",
        ],
        "Exp - 6Z",
        "Repairs and maintenance",
        "review_only",
        "medium",
        "Capital improvements at 6Z should be added back at Item 7W and considered under capital allowances/capital works.",
        "Mapped repairs/maintenance to Item 6Z review.",
    ),

    R(
        [
            r"\bunrealised loss\b",
            r"\bunrealized loss\b",
            r"\bfair value loss\b",
            r"\brevaluation loss\b",
        ],
        "Exp - 6G",
        "Unrealised losses on revaluation of assets to fair value",
        "review_only",
        "medium",
        "If not deductible, add back at Item 7W. Capital losses are not deducted as ordinary expenses.",
        "Mapped unrealised/fair-value loss to Item 6G review.",
        "7W",
    ),

    R(
        [
            r"\bloss.*disposal\b",
            r"\bloss.*sale.*asset\b",
            r"\basset disposal loss\b",
        ],
        "Exp - 6S",
        "All other expenses - disposal loss review",
        "review_only",
        "medium",
        "Accounting loss on depreciating/capital asset may need add-back at Item 7W and tax balancing adjustment at Item 7X or capital loss schedule.",
        "Mapped disposal loss to 6S and Item 7 review.",
        "7W",
    ),

    R(
        [
            r"\bwages\b",
            r"\bsalaries\b",
            r"\bsalary\b",
            r"\bpayroll\b",
            r"\bstaff costs?\b",
            r"\bemployee costs?\b",
            r"\bemployment costs?\b",
            r"\bholiday leave\b",
            r"\bannual leave\b",
            r"\blong service leave\b",
            r"\bleave accrual\b",
            r"\bleave taken\b",
        ],
        "Exp - 6S",
        "All other expenses - salary and wages",
        "financial_label_only",
        "high",
        "Salaries/wages generally go to Item 6S and also support Item 8D salary/wages disclosure. Do not map wages to Item 6D; 6D is superannuation.",
        "Mapped salary/wage/leave account to Item 6S. Consider separate Item 8D-sw support.",
    ),

    # ------------------------------------------------------------------
    # E. Expanded 6S fallback
    # ------------------------------------------------------------------

    R(
        [
            r"\baccounting\b",
            r"\bbookkeeping\b",
            r"\btax agent\b",
            r"\baudit fee\b",
            r"\blegal\b",
            r"\bprofessional fee\b",
            r"\bprofessional fees\b",

            # Marketing / advertising / promo
            r"\badvertising\b",
            r"\btrade advertising\b",
            r"\bmarketing\b",
            r"\bmarketing stock\b",
            r"\bpromotion\b",
            r"\bpromotional\b",
            r"\bpromotional events?\b",
            r"\bpromotional giveaway\b",
            r"\bgiveaway\b",
            r"\bevent prizes?\b",
            r"\bprizes? giveaway\b",
            r"\btrade show\b",
            r"\btrade show expenses?\b",
            r"\bpublic relations\b",
            r"\bpr expenses?\b",
            r"\bmedia\b",
            r"\bcatalogues?\b",
            r"\bart work\b",
            r"\bartwork\b",
            r"\bonline content\b",
            r"\bphotography\b",
            r"\bscreen printing\b",
            r"\binfluencer\b",
            r"\bvik gear\b",
            r"\bamazon fees?\b",

            # Admin / general
            r"\btelephone\b",
            r"\binternet\b",
            r"\bmobile\b",
            r"\bcommunication\b",
            r"\bbank fees?\b",
            r"\bmerchant fees?\b",
            r"\btransaction fees?\b",
            r"\bcard fees?\b",
            r"\binsurance\b",
            r"\bdues\b",
            r"\bsubscriptions?\b",
            r"\bsoftware\b",
            r"\blicen[cs]e fee\b",
            r"\btravel\b",
            r"\baccommodation\b",
            r"\bairfare\b",
            r"\bflight\b",
            r"\bfreight out\b",
            r"\boutbound freight\b",
            r"\bdelivery expense\b",
            r"\bcourier\b",
            r"\bpostage\b",
            r"\bprinting\b",
            r"\bstationery\b",
            r"\boffice expense\b",
            r"\bgeneral expense\b",
            r"\badmin\b",
            r"\badministration\b",
            r"\bcleaning\b",
            r"\butilities\b",
            r"\belectricity\b",
            r"\bwater\b",
            r"\btraining\b",
            r"\brecruitment\b",
            r"\bmembership\b",
        ],
        "Exp - 6S",
        "All other expenses",
        "financial_label_only",
        "medium",
        "Review if material, unusual, private, capital or non-deductible.",
        "Mapped ordinary operating/marketing/admin expense to Item 6S.",
    ),
]
# ---------------------------------------------------------------------------
# B. Balance sheet and Item 8 support rules
# ---------------------------------------------------------------------------

BS_TOTAL_RULES: list[LabelRule] = [
    R([r"^total current assets$", r"^current assets$"], "8D", "All current assets", "financial_label_only", "high", "", "Matched Balance Sheet total current assets to Item 8D."),
    R([r"^total assets$", r"^assets$"], "8E", "Total assets", "financial_label_only", "high", "", "Matched Balance Sheet total assets to Item 8E."),
    R([r"^total current liabilities$", r"^current liabilities$"], "8G", "All current liabilities", "financial_label_only", "high", "", "Matched Balance Sheet total current liabilities to Item 8G."),
    R([r"^total liabilities$", r"^liabilities$"], "8H", "Total liabilities", "financial_label_only", "high", "", "Matched Balance Sheet total liabilities to Item 8H."),
]

BS_DETAIL_RULES: list[LabelRule] = [
    R([r"\btrade debtors?\b", r"\bdebtors?\b", r"accounts? receivable", r"trade receivable", r"customer receivable"], "8C", "Trade debtors", "financial_label_only", "high", "Confirm debtor balance and classification at year end.", "Matched receivable/debtor account to Item 8C."),
    R([r"\btrade creditors?\b", r"\bcreditors?\b", r"accounts? payable", r"trade payable", r"supplier payable"], "8F", "Trade creditors", "financial_label_only", "high", "Confirm creditor balance and classification at year end.", "Matched payable/creditor account to Item 8F."),
    R([r"\bstock\b", r"\binventory\b", r"stock on hand", r"trading stock", r"inventory in transit", r"obsolete stock"], "8B", "Closing stock", "review_only", "medium", "Check closing stock valuation and whether small business trading stock rules apply.", "Matched stock/inventory account to Item 8B review."),
    R([r"\bloan\b", r"borrowings?", r"finance liability", r"trade finance", r"working capital", r"hire purchase", r"chattel mortgage", r"lease liability", r"bank facility", r"interest bearing"], "8J", "Total debt", "review_only", "medium", "Confirm whether this balance is included in Item 8J total debt.", "Matched debt/finance account to Item 8J review."),
    R([r"loan to shareholder", r"loan to director", r"shareholder loan", r"director loan", r"division 7a", r"div ?7a"], "8N", "Loans to shareholders and associates", "review_only", "medium", "Review Division 7A and related-party disclosure.", "Matched shareholder/director loan to Item 8N review."),
    R([r"\bbank\b", r"\bcash\b", r"cheque account", r"business saver", r"savings account", r"paypal", r"stripe", r"airwallex", r"undeposited funds", r"petty cash", r"amex account"], "", "Cash / bank support", "support_only", "high", "", "Cash/bank supports current assets but is not itself a direct Item 8 label."),
    R([r"prepayment", r"prepaid", r"supplier prepayments", r"\bdeposit\b", r"deposits paid", r"security deposit", r"bond", r"other current asset"], "", "Current asset support - review", "review_only", "medium", "Check classification and tax timing adjustment if relevant.", "Matched current asset support account."),
    R([r"tax refund due", r"income tax refund", r"ato receivable", r"gst receivable", r"bas receivable"], "", "Tax receivable support - review", "review_only", "medium", "Agree to ATO/BAS/income tax records.", "Tax receivable supports current assets but is not trade debtors."),
    R([r"property, plant", r"\bppe\b", r"\bplant\b", r"equipment", r"computer", r"it equipment", r"motor vehicle", r"\bvehicle\b", r"furniture", r"fittings", r"leasehold improvement", r"right of use asset", r"rou asset"], "", "Fixed asset support", "support_only", "medium", "Agree to fixed asset register and tax depreciation schedule if material.", "Fixed asset account supports total assets and capital allowance review."),
    R([r"accum dep", r"acc dep", r"accumulated depreciation", r"accumulated amortisation", r"accumulated amortization", r"depn", r"amortisation", r"amortization"], "", "Accumulated depreciation/amortisation support", "support_only", "medium", "Agree to fixed asset register and tax depreciation schedule if material.", "Contra asset account supports net asset balance."),
    R([r"goodwill", r"intangible", r"patent", r"trademark", r"trade mark", r"website", r"software asset", r"development cost"], "", "Intangible asset support - review", "review_only", "medium", "Review amortisation, impairment and tax treatment.", "Matched intangible asset account."),
    R([r"credit card", r"amex", r"visa", r"mastercard", r"current liability", r"other current liabilit"], "", "Current liability support", "support_only", "medium", "Confirm current liability classification.", "Supports current liabilities but is not itself total current liabilities."),
    R([r"\bgst\b", r"\bbas\b", r"payg", r"withholding", r"ato payable", r"income tax payable", r"tax payable", r"input tax", r"output tax", r"vat", r"sales tax"], "", "Tax payable support - review", "review_only", "medium", "Agree BAS/GST/PAYG/income tax balances to lodgements.", "Tax payable account supports current liabilities and tax reconciliation review."),
    R([r"superannuation payable", r"super payable", r"payroll payable", r"wages payable", r"workers compensation payable", r"payroll clearing"], "", "Payroll liability support - review", "review_only", "medium", "Check payment timing where relevant.", "Payroll liability may affect timing or deductibility review."),
    R([r"provision", r"accrual", r"accrued", r"audit fee accrual", r"general accruals", r"employee entitlement", r"annual leave", r"long service leave"], "", "Provision/accrual support - review", "review_only", "medium", "Check deductibility and timing treatment.", "Provision/accrual balances often need tax timing review."),
    R([r"intercompany", r"related party", r"loan from director", r"owed to", r"owed from"], "", "Related-party balance - review", "review_only", "medium", "Review Division 7A, related-party disclosure and debt classification if applicable.", "Matched related-party/intercompany balance."),
    R([r"retained earnings", r"current year earnings", r"ytd net income", r"share capital", r"owner.*equity", r"shareholder", r"drawings", r"reserves", r"dividend declared", r"dividends payable"], "", "Equity support", "support_only", "medium", "", "Equity account supports balance sheet checks; not a direct Item 8 financial label."),
]

SECTION_FALLBACKS: dict[str, dict[str, LabelRule]] = {
    "profit_and_loss": {
        "sales": R(
            [],
            "Inc - 6C",
            "Other sales of goods and services",
            "financial_label_only",
            "medium",
            "",
            "No keyword match; mapped from P&L sales section.",
        ),
        "trading income": R(
            [],
            "Inc - 6C",
            "Other sales of goods and services",
            "financial_label_only",
            "medium",
            "",
            "No keyword match; mapped from P&L trading income section.",
        ),
        "income": R(
            [],
            "Inc - 6C",
            "Other sales of goods and services",
            "financial_label_only",
            "medium",
            "",
            "No keyword match; mapped from P&L income section.",
        ),
        "revenue": R(
            [],
            "Inc - 6C",
            "Other sales of goods and services",
            "financial_label_only",
            "medium",
            "",
            "No keyword match; mapped from P&L revenue section.",
        ),
        "freight income": R(
            [],
            "Inc - 6C",
            "Other sales of goods and services",
            "financial_label_only",
            "medium",
            "",
            "No keyword match; mapped from P&L freight income section.",
        ),
        "customisation income": R(
            [],
            "Inc - 6C",
            "Other sales of goods and services",
            "financial_label_only",
            "medium",
            "",
            "No keyword match; mapped from P&L customisation income section.",
        ),
        "customization income": R(
            [],
            "Inc - 6C",
            "Other sales of goods and services",
            "financial_label_only",
            "medium",
            "",
            "No keyword match; mapped from P&L customization income section.",
        ),
        "other income": R(
            [],
            "Inc - 6R",
            "Other gross income",
            "review_only",
            "medium",
            "Review assessability and whether a more specific Item 6 label applies.",
            "No keyword match; mapped from P&L other income section.",
        ),
        "plus other income": R(
            [],
            "Inc - 6R",
            "Other gross income",
            "review_only",
            "medium",
            "Review assessability and whether a more specific Item 6 label applies.",
            "No keyword match; mapped from P&L other income section.",
        ),

        "cost of sales": R(
            [],
            "Exp - 6A",
            "Cost of sales",
            "financial_label_only",
            "medium",
            "Review stock treatment if material.",
            "No keyword match; mapped from P&L cost of sales section.",
        ),
        "less cost of sales": R(
            [],
            "Exp - 6A",
            "Cost of sales",
            "financial_label_only",
            "medium",
            "Review stock treatment if material.",
            "No keyword match; mapped from P&L cost of sales section.",
        ),
        "cost of goods sold": R(
            [],
            "Exp - 6A",
            "Cost of sales",
            "financial_label_only",
            "medium",
            "Review stock treatment if material.",
            "No keyword match; mapped from P&L cost of goods sold section.",
        ),

        "expenses": R(
            [],
            "Exp - 6S",
            "All other expenses",
            "financial_label_only",
            "low",
            "No keyword match; review account classification.",
            "No keyword match; mapped from P&L expenses section.",
        ),
        "operating expenses": R(
            [],
            "Exp - 6S",
            "All other expenses",
            "financial_label_only",
            "low",
            "No keyword match; review account classification.",
            "No keyword match; mapped from P&L operating expenses section.",
        ),
        "less operating expenses": R(
            [],
            "Exp - 6S",
            "All other expenses",
            "financial_label_only",
            "low",
            "No keyword match; review account classification.",
            "No keyword match; mapped from P&L operating expenses section.",
        ),
    },

    "balance_sheet": {
        "current assets": R([], "", "Current asset support", "support_only", "medium", "", "No keyword match; labelled from Balance Sheet section."),
        "non current assets": R([], "", "Non-current asset support", "support_only", "medium", "Agree to asset schedule if material.", "No keyword match; labelled from Balance Sheet section."),
        "fixed assets": R([], "", "Fixed asset support", "support_only", "medium", "Agree to asset schedule if material.", "No keyword match; labelled from Balance Sheet section."),
        "current liabilities": R([], "", "Current liability support", "support_only", "medium", "", "No keyword match; labelled from Balance Sheet section."),
        "non current liabilities": R([], "", "Non-current liability support", "support_only", "medium", "Review debt classification.", "No keyword match; labelled from Balance Sheet section."),
        "equity": R([], "", "Equity support", "support_only", "medium", "", "No keyword match; labelled from Balance Sheet section."),
    },
}
# ---------------------------------------------------------------------------
# C. Helpers
# ---------------------------------------------------------------------------

def _normalise_rule_text(value: object) -> str:
    text = str(value or "").strip().lower()

    if text in {"nan", "none"}:
        return ""

    text = text.replace("&", " and ")

    # Normalise dash/slash/underscore characters.
    text = re.sub(r"[\u2010-\u2015\u2212\-_\/]+", " ", text)

    # Keep letters, numbers and spaces only.
    text = re.sub(r"[^\w\s]", " ", text)

    # Collapse spaces.
    text = re.sub(r"\s+", " ", text).strip()

    # Remove leading account code:
    # "40100 yachting sales" -> "yachting sales"
    text = re.sub(r"^\d{3,}\s+", "", text)

    return text


def _match_rules(text: str, rules: Iterable[LabelRule]) -> dict[str, str] | None:
    for rule in rules:
        for pattern in rule.patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return rule.as_mapping()
    return None


def _with_section_reason(mapping: dict[str, str], report_section: str) -> dict[str, str]:
    result = dict(mapping)
    result["Label Reason"] = f"{result['Label Reason']} Section={report_section!r}."
    return result


def _unmapped(account_name: str, report_type: str, report_section: str = "") -> dict[str, str]:
    return {
        "ITR Ref": "Review",
        "ITR Label": "Unmapped account - review",
        "Treatment": "unmapped",
        "Confidence": "low",
        "Review Note": "No safe ATO label match. Review account name, report section and source records.",
        "Label Reason": f"No rule matched account={account_name!r}, report_type={report_type!r}, section={report_section!r}.",
        "Recon ITR Ref": "",
    }


# ---------------------------------------------------------------------------
# D. Public API
# ---------------------------------------------------------------------------

def match_financial_label(
    account_name: str,
    report_type: str,
    report_section: str = "",
) -> dict[str, str]:
    """Return conservative ITR mapping for a report row.

    The return shape is intentionally compatible with your current workbook code:
    ITR Ref, ITR Label, Treatment, Confidence, Review Note, Label Reason,
    Recon ITR Ref.
    """
    text = _normalise_rule_text(account_name)
    section = _normalise_rule_text(report_section)
    normalised_report_type = _normalise_rule_text(report_type).replace(" ", "_")

    if normalised_report_type in {"profit_loss", "p_l", "pl", "profit_and_loss"}:
        report = "profit_and_loss"
    elif normalised_report_type in {"balance_sheet", "bs"}:
        report = "balance_sheet"
    else:
        report = normalised_report_type

    if report == "profit_and_loss":
        matched = _match_rules(text, PL_RULES)
        if matched:
            return matched

        fallback = SECTION_FALLBACKS["profit_and_loss"].get(section)
        if fallback:
            return _with_section_reason(fallback.as_mapping(), report_section)

        return _unmapped(account_name, report_type, report_section)

    if report == "balance_sheet":
        # Totals must be tested before detail accounts.
        matched = _match_rules(text, BS_TOTAL_RULES)
        if matched:
            return matched

        matched = _match_rules(text, BS_DETAIL_RULES)
        if matched:
            return matched

        # Section-aware fallback, using contains checks because Xero sections vary.
        if "receivable" in section or "debtor" in section:
            return _with_section_reason(R([], "8C", "Trade debtors", "financial_label_only", "medium", "Confirm trade debtor classification.", "No keyword match; labelled from Balance Sheet section.").as_mapping(), report_section)
        if "inventory" in section or "stock" in section:
            return _with_section_reason(R([], "8B", "Closing stock", "review_only", "medium", "Check closing stock valuation and tax treatment.", "No keyword match; labelled from Balance Sheet section.").as_mapping(), report_section)
        if "payable" in section or "creditor" in section:
            return _with_section_reason(R([], "8F", "Trade creditors", "financial_label_only", "medium", "Confirm trade creditor classification.", "No keyword match; labelled from Balance Sheet section.").as_mapping(), report_section)
        if "loan" in section or "borrow" in section or "debt" in section:
            return _with_section_reason(R([], "8J", "Total debt", "review_only", "medium", "Confirm whether this belongs in total debt.", "No keyword match; labelled from Balance Sheet section.").as_mapping(), report_section)

        for key, rule in SECTION_FALLBACKS["balance_sheet"].items():
            if key in section:
                return _with_section_reason(rule.as_mapping(), report_section)

        return _unmapped(account_name, report_type, report_section)

    return _unmapped(account_name, report_type, report_section)


def should_highlight_mapping(mapping: dict[str, str], report_type: str = "") -> bool:
    """Return True when the workbook row should be visually reviewed."""
    itr_ref = str(mapping.get("ITR Ref", "") or "").strip()
    treatment = str(mapping.get("Treatment", "") or "").strip().lower()
    confidence = str(mapping.get("Confidence", "") or "").strip().lower()
    recon_ref = str(mapping.get("Recon ITR Ref", "") or "").strip()
    review_note = str(mapping.get("Review Note", "") or "").strip()
    normalised_report_type = _normalise_rule_text(report_type).replace(" ", "_")

    if itr_ref == "Review" or treatment == "unmapped":
        return True

    if confidence == "low":
        return True

    if recon_ref:
        return True

    if treatment == "review_only":
        return True

    # Do not highlight ordinary medium-confidence label-only mappings.
    # Example:
    # Exp - 6S marketing/admin accounts
    # Exp - 6C consultants
    # Inc - 6C sales/service income
    if treatment == "financial_label_only":
        return False

    if normalised_report_type in {"balance_sheet", "bs"} and treatment == "support_only":
        return False

    return bool(review_note)


def is_tax_reconciliation_item(mapping: dict[str, str]) -> bool:
    """Return True if the matched row may feed Item 7 reconciliation review."""
    return bool(mapping.get("Recon ITR Ref", "").strip())


def get_reconciliation_ref(mapping: dict[str, str]) -> str:
    """Return the Item 7 reconciliation reference, if any."""
    return mapping.get("Recon ITR Ref", "").strip()


def is_auto_safe_mapping(mapping: dict[str, str]) -> bool:
    """Return True only for high-confidence, non-review mappings."""
    return (
        mapping.get("Treatment") == "financial_label_only"
        and mapping.get("Confidence") == "high"
        and not mapping.get("Recon ITR Ref")
        and mapping.get("ITR Ref") not in {"Review", ""}
    )
def match_account_to_itr(account_name: str, report_type: str) -> dict[str, str]:
    """Backward-compatible wrapper for older scripts."""
    result = match_financial_label(account_name, report_type)

    return {
        "itr_ref": result.get("ITR Ref", ""),
        "category": result.get("ITR Label", ""),
        "review_note": result.get("Review Note", ""),
        "decision_logic": result.get("Label Reason", ""),
    }