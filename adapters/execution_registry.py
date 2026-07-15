"""Bind the repository's existing adapters to typed execution contracts.

The executable core does not import this module, so its wheel remains dependency-free.
Callers explicitly provide initialized adapter instances and choose whether they use
cache, local compute, or live endpoints.
"""

from __future__ import annotations

from typing import Any

from agentic_drug_discovery.execution import (
    ExecutionMode,
    ToolContract,
    ToolRegistry,
    ToolResponse,
    ToolStatus,
)
from agentic_drug_discovery.models import (
    ActionType,
    SourceReference,
    Stage,
    to_primitive,
)


OPEN_TARGETS_SOURCE = SourceReference(
    source_id="open-targets-platform",
    source_version="runtime-cache-or-live-unpinned",
    locator="https://api.platform.opentargets.org/api/v4/graphql",
)
CHEMBL_SOURCE = SourceReference(
    source_id="chembl",
    source_version="runtime-cache-or-live-unpinned",
    locator="https://www.ebi.ac.uk/chembl/api/data",
)
CTGOV_SOURCE = SourceReference(
    source_id="clinicaltrials-gov",
    source_version="runtime-cache-or-live-unpinned",
    locator="https://clinicaltrials.gov/api/v2/studies",
)
EMA_SOURCE = SourceReference(
    source_id="ema-medicines-output",
    source_version="runtime-cache-or-live-unpinned",
    locator=(
        "https://www.ema.europa.eu/en/documents/report/"
        "medicines-output-medicines-report_en.xlsx"
    ),
)
BOLTZ_SOURCE = SourceReference(
    source_id="boltz2-service",
    source_version="runtime-endpoint-unpinned",
    locator="configured:BOLTZ_ENDPOINT",
)
RDKit_SOURCE = SourceReference(
    source_id="rdkit",
    source_version="runtime-local-unpinned",
    locator="local:rdkit",
)


def _payload(value: Any, *, key: str = "result") -> dict[str, Any]:
    primitive = to_primitive(value)
    if isinstance(primitive, dict):
        return primitive
    return {key: primitive}


def _success(
    value: Any,
    *,
    source: SourceReference,
    mode: ExecutionMode,
    message: str,
    key: str = "result",
) -> ToolResponse:
    return ToolResponse(
        status=ToolStatus.SUCCEEDED,
        payload=_payload(value, key=key),
        execution_mode=mode,
        sources=(source,),
        message=message,
    )


def _unavailable(
    value: Any,
    *,
    code: str,
    source: SourceReference,
    mode: ExecutionMode,
    message: str,
    key: str = "result",
) -> ToolResponse:
    return ToolResponse(
        status=ToolStatus.UNAVAILABLE,
        payload=_payload(value, key=key),
        execution_mode=mode,
        sources=(source,),
        error_code=code,
        message=message,
    )


def _failed(
    value: Any,
    *,
    code: str,
    source: SourceReference,
    mode: ExecutionMode,
    message: str,
    key: str = "result",
) -> ToolResponse:
    return ToolResponse(
        status=ToolStatus.FAILED,
        payload=_payload(value, key=key),
        execution_mode=mode,
        sources=(source,),
        error_code=code,
        message=message,
    )


def _pinned_sources(profile: Any) -> tuple[SourceReference, ...]:
    records = profile.get("records") if isinstance(profile, dict) else None
    if not isinstance(records, (list, tuple)):
        raise ValueError("pinned evidence profile records must be a sequence")
    by_id: dict[str, SourceReference] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("source"), dict):
            raise ValueError("pinned evidence records require source objects")
        value = record["source"]
        source = SourceReference(
            source_id=value["source_id"],
            source_version=value["source_version"],
            locator=value["locator"],
            content_hash=value["content_hash"],
        )
        previous = by_id.get(source.source_id)
        if previous is not None and previous != source:
            raise ValueError("one source_id cannot identify conflicting source records")
        by_id[source.source_id] = source
    return tuple(by_id.values())


def _pinned_profile_response(
    profile: Any,
    *,
    incomplete_code: str,
    ambiguous_code: str,
    success_message: str,
) -> ToolResponse:
    payload = _payload(profile)
    sources = _pinned_sources(payload)
    status = payload.get("status")
    if status == "resolved":
        return ToolResponse(
            status=ToolStatus.SUCCEEDED,
            payload=payload,
            execution_mode=ExecutionMode.CACHE,
            sources=sources,
            message=success_message,
        )
    if status == "incomplete":
        return ToolResponse(
            status=ToolStatus.UNAVAILABLE,
            payload=payload,
            execution_mode=ExecutionMode.CACHE,
            sources=sources,
            error_code=incomplete_code,
            message="Required source-pinned evidence records are incomplete.",
        )
    return ToolResponse(
        status=ToolStatus.FAILED,
        payload=payload,
        execution_mode=ExecutionMode.CACHE,
        sources=sources,
        error_code=ambiguous_code,
        message="Source-pinned evidence records are ambiguous or invalid.",
    )


def _register_opentargets(registry: ToolRegistry, adapter: Any) -> None:
    disease_contract = ToolContract(
        tool_id="opentargets",
        operation="disease_profile",
        action_type=ActionType.QUERY_DATABASE,
        description="Resolve disease identity and associated-target page metadata.",
        allowed_stages=(Stage.DISEASE_CONTEXT,),
        optional_arguments=("disease_efo",),
        default_cost=0.05,
    )

    def disease_handler(arguments):
        if not hasattr(adapter, "disease_profile"):
            return _unavailable(
                {},
                code="opentargets_disease_profile_unsupported",
                source=OPEN_TARGETS_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="This Open Targets adapter lacks a structured disease profile.",
            )
        result = adapter.disease_profile(arguments.get("disease_efo"))
        if result.get("evidence_status") == "adapter_disease_mismatch":
            return _failed(
                result,
                code="opentargets_disease_context_mismatch",
                source=OPEN_TARGETS_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="Requested disease does not match the initialized adapter dataset.",
            )
        if result.get("evidence_status") == "dataset_unavailable":
            return _unavailable(
                result,
                code="opentargets_dataset_unavailable",
                source=OPEN_TARGETS_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="Open Targets disease data were unavailable.",
            )
        if result.get("resolved") is not True:
            return _unavailable(
                result,
                code="opentargets_disease_unresolved",
                source=OPEN_TARGETS_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="Open Targets disease identity was unresolved.",
            )
        return _success(
            result,
            source=OPEN_TARGETS_SOURCE,
            mode=ExecutionMode.UNKNOWN,
            message="Open Targets disease profile query completed.",
        )

    registry.register(disease_contract, disease_handler)

    association_contract = ToolContract(
        tool_id="opentargets",
        operation="target_disease_association",
        action_type=ActionType.QUERY_DATABASE,
        description="Retrieve one target-disease association record.",
        allowed_stages=(Stage.DISEASE_CONTEXT, Stage.TARGET_NOMINATION),
        required_arguments=("symbol", "disease_efo"),
        default_cost=0.1,
    )

    def association_handler(arguments):
        result = adapter.target_disease_association(
            arguments["symbol"], arguments["disease_efo"]
        )
        if result.get("evidence_status") == "adapter_disease_mismatch":
            return _failed(
                result,
                code="opentargets_disease_context_mismatch",
                source=OPEN_TARGETS_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="Requested disease does not match the initialized adapter dataset.",
            )
        if result.get("evidence_status") == "dataset_unavailable":
            return _unavailable(
                result,
                code="opentargets_dataset_unavailable",
                source=OPEN_TARGETS_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="Open Targets association data were unavailable.",
            )
        return _success(
            result,
            source=OPEN_TARGETS_SOURCE,
            mode=ExecutionMode.UNKNOWN,
            message="Open Targets association query completed.",
        )

    registry.register(association_contract, association_handler)


def _register_chembl(registry: ToolRegistry, adapter: Any) -> None:
    stages = (
        Stage.TARGET_NOMINATION,
        Stage.MODALITY_SELECTION,
        Stage.CANDIDATE_GENERATION,
        Stage.LEAD_OPTIMIZATION,
    )
    molecule_contract = ToolContract(
        tool_id="chembl",
        operation="molecule",
        action_type=ActionType.QUERY_DATABASE,
        description="Resolve a ChEMBL molecule by identifier or name.",
        allowed_stages=stages,
        optional_arguments=("chembl_id", "name"),
        default_cost=0.1,
    )

    def molecule_handler(arguments):
        if not arguments.get("chembl_id") and not arguments.get("name"):
            return _failed(
                {},
                code="chembl_identifier_missing",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="A ChEMBL id or molecule name is required.",
            )
        result = adapter.molecule(
            chembl_id=arguments.get("chembl_id"), name=arguments.get("name")
        )
        if not result or not result.get("found"):
            return _unavailable(
                result or {},
                code="chembl_molecule_unresolved",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message=(
                    "ChEMBL returned no resolved molecule; the legacy adapter cannot "
                    "distinguish a true no-match from retrieval failure."
                ),
            )
        return _success(
            result,
            source=CHEMBL_SOURCE,
            mode=ExecutionMode.UNKNOWN,
            message="ChEMBL molecule lookup completed.",
        )

    registry.register(molecule_contract, molecule_handler)

    mechanism_contract = ToolContract(
        tool_id="chembl",
        operation="mechanism",
        action_type=ActionType.QUERY_DATABASE,
        description="Retrieve mechanism records for a ChEMBL molecule.",
        allowed_stages=stages,
        required_arguments=("chembl_id",),
        default_cost=0.1,
    )

    def mechanism_handler(arguments):
        result = adapter.mechanism(arguments["chembl_id"])
        if not result:
            return _unavailable(
                [],
                key="items",
                code="chembl_mechanism_unresolved",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message=(
                    "No mechanism rows were returned; the legacy adapter cannot "
                    "distinguish no-match from retrieval failure."
                ),
            )
        return _success(
            result,
            key="items",
            source=CHEMBL_SOURCE,
            mode=ExecutionMode.UNKNOWN,
            message="ChEMBL mechanism lookup completed.",
        )

    registry.register(mechanism_contract, mechanism_handler)

    modality_contract = ToolContract(
        tool_id="chembl",
        operation="molecule_mechanism_profile",
        action_type=ActionType.QUERY_DATABASE,
        description="Resolve one molecule together with its ChEMBL mechanism rows.",
        allowed_stages=(Stage.MODALITY_SELECTION,),
        required_arguments=("chembl_id",),
        default_cost=0.2,
    )

    def modality_handler(arguments):
        molecule = adapter.molecule(chembl_id=arguments["chembl_id"])
        if not molecule or not molecule.get("found"):
            return _unavailable(
                {"molecule": molecule or {}, "items": []},
                code="chembl_molecule_unresolved",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="ChEMBL molecule identity was unresolved.",
            )
        mechanisms = adapter.mechanism(arguments["chembl_id"])
        if not mechanisms:
            return _unavailable(
                {"molecule": molecule, "items": []},
                code="chembl_mechanism_unresolved",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="ChEMBL returned no mechanism rows for the resolved molecule.",
            )
        return _success(
            {"molecule": molecule, "items": mechanisms},
            source=CHEMBL_SOURCE,
            mode=ExecutionMode.UNKNOWN,
            message="ChEMBL molecule and mechanism profile lookup completed.",
        )

    registry.register(modality_contract, modality_handler)

    target_modality_contract = ToolContract(
        tool_id="chembl",
        operation="molecule_target_mechanism_profile",
        action_type=ActionType.QUERY_DATABASE,
        description=(
            "Resolve a molecule, mechanism rows, and the declared ChEMBL target "
            "identity profile."
        ),
        allowed_stages=(Stage.MODALITY_SELECTION,),
        required_arguments=("chembl_id", "target_id", "target_record_id"),
        default_cost=0.25,
    )

    def target_modality_handler(arguments):
        if not hasattr(adapter, "target"):
            return _unavailable(
                {"molecule": {}, "items": [], "target": {}},
                code="chembl_target_profile_unsupported",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="This ChEMBL adapter lacks a structured target profile.",
            )
        molecule = adapter.molecule(chembl_id=arguments["chembl_id"])
        if not molecule or not molecule.get("found"):
            return _unavailable(
                {"molecule": molecule or {}, "items": [], "target": {}},
                code="chembl_molecule_unresolved",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="ChEMBL molecule identity was unresolved.",
            )
        mechanisms = adapter.mechanism(arguments["chembl_id"])
        if not mechanisms:
            return _unavailable(
                {"molecule": molecule, "items": [], "target": {}},
                code="chembl_mechanism_unresolved",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="ChEMBL returned no mechanism rows for the resolved molecule.",
            )
        target = adapter.target(arguments["target_id"])
        if not target or not target.get("found"):
            return _unavailable(
                {"molecule": molecule, "items": mechanisms, "target": target or {}},
                code="chembl_target_unresolved",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="ChEMBL target identity was unresolved.",
            )
        return _success(
            {"molecule": molecule, "items": mechanisms, "target": target},
            source=CHEMBL_SOURCE,
            mode=ExecutionMode.UNKNOWN,
            message="ChEMBL molecule, target, and mechanism profile lookup completed.",
        )

    registry.register(target_modality_contract, target_modality_handler)

    activity_contract = ToolContract(
        tool_id="chembl",
        operation="target_activity_count",
        action_type=ActionType.QUERY_DATABASE,
        description="Retrieve the ChEMBL activity count for a target.",
        allowed_stages=(*stages, Stage.PRECLINICAL_VALIDATION),
        required_arguments=("target_id",),
        default_cost=0.1,
    )

    def activity_handler(arguments):
        result = adapter.target_activity_count(arguments["target_id"])
        if result is None:
            return _unavailable(
                {"count": None},
                code="chembl_activity_count_unavailable",
                source=CHEMBL_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="ChEMBL target activity count was unavailable.",
            )
        return _success(
            {"count": result},
            source=CHEMBL_SOURCE,
            mode=ExecutionMode.UNKNOWN,
            message="ChEMBL target activity count lookup completed.",
        )

    registry.register(activity_contract, activity_handler)


def _register_pinned_evidence(registry: ToolRegistry, adapter: Any) -> None:
    disease_contract = ToolContract(
        tool_id="pinned_evidence",
        operation="disease_unmet_need",
        action_type=ActionType.QUERY_DATABASE,
        description=(
            "Retrieve independent source-pinned disease-burden and treatment-gap "
            "records."
        ),
        allowed_stages=(Stage.DISEASE_CONTEXT,),
        required_arguments=("disease_id",),
        default_cost=0.05,
    )

    def disease_handler(arguments):
        return _pinned_profile_response(
            adapter.disease_unmet_need(arguments["disease_id"]),
            incomplete_code="pinned_unmet_need_incomplete",
            ambiguous_code="pinned_unmet_need_ambiguous",
            success_message="Pinned disease unmet-need evidence lookup completed.",
        )

    registry.register(disease_contract, disease_handler)

    function_contract = ToolContract(
        tool_id="pinned_evidence",
        operation="candidate_functional_effect",
        action_type=ActionType.QUERY_DATABASE,
        description=(
            "Retrieve independent source-pinned candidate-target functional and "
            "disease-model effect records."
        ),
        allowed_stages=(Stage.PRECLINICAL_VALIDATION,),
        required_arguments=("candidate_id", "target_id", "disease_id"),
        default_cost=0.1,
    )

    def function_handler(arguments):
        return _pinned_profile_response(
            adapter.candidate_functional_effect(
                arguments["candidate_id"],
                arguments["target_id"],
                arguments["disease_id"],
            ),
            incomplete_code="pinned_functional_effect_incomplete",
            ambiguous_code="pinned_functional_effect_ambiguous",
            success_message="Pinned candidate functional-effect lookup completed.",
        )

    registry.register(function_contract, function_handler)

    clinical_contract = ToolContract(
        tool_id="pinned_evidence",
        operation="clinical_trial_design",
        action_type=ActionType.QUERY_DATABASE,
        description=(
            "Retrieve one source-pinned ClinicalTrials.gov arm, population, and "
            "posted-endpoint design record."
        ),
        allowed_stages=(Stage.CLINICAL_STRATEGY,),
        required_arguments=("candidate_id", "disease_id", "trial_id"),
        default_cost=0.1,
    )

    def clinical_handler(arguments):
        return _pinned_profile_response(
            adapter.clinical_trial_design(
                arguments["candidate_id"],
                arguments["disease_id"],
                arguments["trial_id"],
            ),
            incomplete_code="pinned_clinical_trial_design_incomplete",
            ambiguous_code="pinned_clinical_trial_design_ambiguous",
            success_message="Pinned clinical trial design lookup completed.",
        )

    registry.register(clinical_contract, clinical_handler)


def _register_clinical_synthesis(registry: ToolRegistry, adapter: Any) -> None:
    mapping_contract = ToolContract(
        tool_id="clinical_synthesis",
        operation="register_endpoint_mapping",
        action_type=ActionType.RUN_VERIFIER,
        description=(
            "Bind a reviewer-approved endpoint-family ontology declaration to exact "
            "clinical trial ledger identities."
        ),
        allowed_stages=(Stage.REGULATORY_POSTMARKET,),
        required_arguments=("spec",),
        default_cost=0.01,
    )

    def mapping_handler(arguments):
        result = adapter.register_endpoint_mapping(arguments["spec"])
        return ToolResponse(
            status=ToolStatus.SUCCEEDED,
            payload=_payload(result),
            execution_mode=ExecutionMode.LOCAL,
            sources=(),
            message="Reviewed endpoint mapping declaration was normalized locally.",
        )

    registry.register(mapping_contract, mapping_handler)

    synthesis_contract = ToolContract(
        tool_id="clinical_synthesis",
        operation="harmonize_benefit_risk",
        action_type=ActionType.RUN_VERIFIER,
        description=(
            "Compile an explicit source-ledger selection into a descriptive, "
            "non-pooled benefit-risk synthesis."
        ),
        allowed_stages=(Stage.REGULATORY_POSTMARKET,),
        required_arguments=("spec",),
        default_cost=0.01,
    )

    def handler(arguments):
        result = adapter.harmonize_benefit_risk(arguments["spec"])
        return ToolResponse(
            status=ToolStatus.SUCCEEDED,
            payload=_payload(result),
            execution_mode=ExecutionMode.LOCAL,
            sources=(),
            message="Reviewed clinical synthesis declaration was normalized locally.",
        )

    registry.register(synthesis_contract, handler)


def _ctgov_has_index(adapter: Any) -> bool | None:
    if not hasattr(adapter, "stats"):
        return None
    stats = adapter.stats()
    count = stats.get("indexed_studies") if isinstance(stats, dict) else None
    return None if count is None else bool(count)


def _register_ctgov(registry: ToolRegistry, adapter: Any) -> None:
    clinical_stages = (Stage.CLINICAL_STRATEGY, Stage.REGULATORY_POSTMARKET)
    search_trials_contract = ToolContract(
        tool_id="ctgov",
        operation="search_trials",
        action_type=ActionType.QUERY_DATABASE,
        description="Search cached ClinicalTrials.gov records by asset and condition.",
        allowed_stages=clinical_stages,
        required_arguments=("drug", "condition"),
        default_cost=0.1,
    )

    def search_trials_handler(arguments):
        result = adapter.search_trials(arguments["drug"], arguments["condition"])
        if not result and _ctgov_has_index(adapter) is False:
            return _unavailable(
                [],
                key="items",
                code="ctgov_dataset_unavailable",
                source=CTGOV_SOURCE,
                mode=ExecutionMode.CACHE,
                message="No ClinicalTrials.gov source records are loaded.",
            )
        return _success(
            result,
            key="items",
            source=CTGOV_SOURCE,
            mode=ExecutionMode.CACHE,
            message="ClinicalTrials.gov pair search completed.",
        )

    registry.register(search_trials_contract, search_trials_handler)

    search_asset_contract = ToolContract(
        tool_id="ctgov",
        operation="search_asset",
        action_type=ActionType.QUERY_DATABASE,
        description="Search ClinicalTrials.gov for an asset across conditions.",
        allowed_stages=clinical_stages,
        required_arguments=("drug",),
        default_cost=0.1,
    )

    def search_asset_handler(arguments):
        result = adapter.search_asset(arguments["drug"])
        mode = (
            ExecutionMode.LIVE
            if getattr(adapter, "live", False)
            else ExecutionMode.CACHE
        )
        if (
            not result
            and not getattr(adapter, "live", False)
            and _ctgov_has_index(adapter) is False
        ):
            return _unavailable(
                [],
                key="items",
                code="ctgov_dataset_unavailable",
                source=CTGOV_SOURCE,
                mode=mode,
                message="No ClinicalTrials.gov source records are loaded.",
            )
        return _success(
            result,
            key="items",
            source=CTGOV_SOURCE,
            mode=mode,
            message="ClinicalTrials.gov asset search completed.",
        )

    registry.register(search_asset_contract, search_asset_handler)

    significance_contract = ToolContract(
        tool_id="ctgov",
        operation="primary_significance",
        action_type=ActionType.QUERY_DATABASE,
        description="Read parsed primary-endpoint significance for one NCT record.",
        allowed_stages=clinical_stages,
        required_arguments=("nct",),
        default_cost=0.05,
    )

    def significance_handler(arguments):
        result = adapter.primary_significance(arguments["nct"])
        if result is None and _ctgov_has_index(adapter) is False:
            return _unavailable(
                {"result": None},
                code="ctgov_dataset_unavailable",
                source=CTGOV_SOURCE,
                mode=ExecutionMode.CACHE,
                message="No ClinicalTrials.gov source records are loaded.",
            )
        return _success(
            {"result": result},
            source=CTGOV_SOURCE,
            mode=ExecutionMode.CACHE,
            message="ClinicalTrials.gov primary-significance lookup completed.",
        )

    registry.register(significance_contract, significance_handler)

    plausibility_contract = ToolContract(
        tool_id="ctgov",
        operation="check_value_plausibility",
        action_type=ActionType.RUN_VERIFIER,
        description="Apply a deterministic numeric plausibility rule to records.",
        allowed_stages=clinical_stages,
        required_arguments=("records", "rule"),
        default_cost=0.0,
    )

    def plausibility_handler(arguments):
        result = adapter.check_value_plausibility(
            arguments["records"], arguments["rule"]
        )
        return _success(
            result,
            key="items",
            source=CTGOV_SOURCE,
            mode=ExecutionMode.LOCAL,
            message="Clinical value plausibility check completed.",
        )

    registry.register(plausibility_contract, plausibility_handler)


def _register_ema(registry: ToolRegistry, adapter: Any) -> None:
    contract = ToolContract(
        tool_id="ema",
        operation="lookup",
        action_type=ActionType.QUERY_DATABASE,
        description="Look up a medicine in the EMA medicines-output table.",
        allowed_stages=(Stage.REGULATORY_POSTMARKET,),
        required_arguments=("query",),
        default_cost=0.1,
    )

    def handler(arguments):
        result = adapter.lookup(arguments["query"])
        status = result.get("evidence_status")
        if status == "dataset_unavailable":
            return _unavailable(
                result,
                code="ema_dataset_unavailable",
                source=EMA_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="EMA medicines-output data were unavailable.",
            )
        if status == "invalid_query":
            return _failed(
                result,
                code="ema_query_invalid",
                source=EMA_SOURCE,
                mode=ExecutionMode.UNKNOWN,
                message="EMA lookup query was invalid.",
            )
        return _success(
            result,
            source=EMA_SOURCE,
            mode=ExecutionMode.UNKNOWN,
            message="EMA medicines-output lookup completed.",
        )

    registry.register(contract, handler)


def _register_ema_ledger(registry: ToolRegistry, adapter: Any) -> None:
    contract = ToolContract(
        tool_id="ema_ledger",
        operation="event",
        action_type=ActionType.QUERY_DATABASE,
        description="Read one curated, source-verified EMA event record.",
        allowed_stages=(Stage.REGULATORY_POSTMARKET,),
        required_arguments=("asset_key",),
        default_cost=0.05,
    )

    def handler(arguments):
        result = adapter.event(arguments["asset_key"])
        if result is None and not getattr(adapter, "events", {}):
            return _unavailable(
                {"result": None},
                code="ema_ledger_unavailable",
                source=EMA_SOURCE,
                mode=ExecutionMode.CACHE,
                message="Curated EMA event ledger is unavailable.",
            )
        return _success(
            {"result": result},
            source=EMA_SOURCE,
            mode=ExecutionMode.CACHE,
            message="Curated EMA event lookup completed.",
        )

    registry.register(contract, handler)


def _register_boltz(registry: ToolRegistry, adapter: Any) -> None:
    contract = ToolContract(
        tool_id="boltz2",
        operation="predict_binding",
        action_type=ActionType.RUN_SFM,
        description="Run a configured Boltz-2 binding/structure prediction.",
        allowed_stages=(
            Stage.CANDIDATE_GENERATION,
            Stage.LEAD_OPTIMIZATION,
            Stage.PRECLINICAL_VALIDATION,
        ),
        required_arguments=("spec",),
        default_cost=1.0,
    )

    def handler(arguments):
        if hasattr(adapter, "predict_binding_record"):
            result = adapter.predict_binding_record(arguments["spec"])
            if not isinstance(result, dict):
                return _failed(
                    {"adapter_status": "invalid_structured_response"},
                    code="boltz_response_contract_invalid",
                    source=BOLTZ_SOURCE,
                    mode=ExecutionMode.UNKNOWN,
                    message="Boltz-2 adapter returned an invalid structured response.",
                )
            status = result.get("status")
            mode = (
                ExecutionMode.LIVE
                if getattr(adapter, "endpoint", None)
                else ExecutionMode.UNKNOWN
            )
            if status == "predicted":
                return _success(
                    result,
                    source=BOLTZ_SOURCE,
                    mode=mode,
                    message="Boltz-2 structured prediction completed.",
                )
            if status in {"unavailable", "proxy_only"}:
                return _unavailable(
                    result,
                    code="boltz_prediction_unavailable",
                    source=BOLTZ_SOURCE,
                    mode=mode,
                    message=(
                        "Boltz-2 prediction was unavailable; proxy metadata was not "
                        "treated as a prediction."
                    ),
                )
            if status == "invalid_input":
                return _failed(
                    {"adapter_status": "invalid_input"},
                    code="boltz_input_invalid",
                    source=BOLTZ_SOURCE,
                    mode=mode,
                    message="Boltz-2 input must contain a target and ligand.",
                )
            return _failed(
                {
                    "adapter_status": (
                        status
                        if status in {"endpoint_error", "invalid_input"}
                        else "invalid_structured_response"
                    )
                },
                code=(
                    "boltz_endpoint_error"
                    if status == "endpoint_error"
                    else "boltz_response_contract_invalid"
                ),
                source=BOLTZ_SOURCE,
                mode=mode,
                message="Boltz-2 structured prediction failed closed.",
            )

        result = adapter.predict_binding(arguments["spec"])
        mode = (
            ExecutionMode.LIVE
            if getattr(adapter, "endpoint", None)
            else ExecutionMode.UNKNOWN
        )
        lower = str(result).lower()
        if "endpoint error" in lower:
            return _failed(
                {"adapter_status": "endpoint_error"},
                code="boltz_endpoint_error",
                source=BOLTZ_SOURCE,
                mode=mode,
                message="Configured Boltz-2 endpoint failed.",
            )
        if "unavailable" in lower or "expected 'target|ligand'" in lower:
            return _unavailable(
                {"text": result},
                code="boltz_prediction_unavailable",
                source=BOLTZ_SOURCE,
                mode=mode,
                message="Boltz-2 prediction was unavailable; no binding claim was produced.",
            )
        return _success(
            {"text": result},
            source=BOLTZ_SOURCE,
            mode=mode,
            message="Boltz-2 prediction completed.",
        )

    registry.register(contract, handler)


def _register_molprops(registry: ToolRegistry, adapter: Any) -> None:
    contract = ToolContract(
        tool_id="molprops",
        operation="properties",
        action_type=ActionType.SCORE_CANDIDATE,
        description="Compute local RDKit molecular-property and Lipinski signals.",
        allowed_stages=(Stage.CANDIDATE_GENERATION, Stage.LEAD_OPTIMIZATION),
        required_arguments=("spec",),
        default_cost=0.05,
    )

    def handler(arguments):
        result = adapter.compute(arguments["spec"])
        if result is None and not getattr(adapter, "ok", False):
            return _unavailable(
                {},
                code="rdkit_unavailable",
                source=RDKit_SOURCE,
                mode=ExecutionMode.LOCAL,
                message="RDKit is not installed; molecular properties were not computed.",
            )
        if result is None:
            return _failed(
                {},
                code="molecular_structure_unresolved",
                source=RDKit_SOURCE,
                mode=ExecutionMode.LOCAL,
                message="Input could not be resolved to a molecular structure.",
            )
        return _success(
            result,
            source=RDKit_SOURCE,
            mode=ExecutionMode.LOCAL,
            message="RDKit molecular-property calculation completed.",
        )

    registry.register(contract, handler)


def register_existing_adapters(
    registry: ToolRegistry,
    *,
    opentargets: Any | None = None,
    chembl: Any | None = None,
    pinned_evidence: Any | None = None,
    clinical_synthesis: Any | None = None,
    ctgov: Any | None = None,
    ema: Any | None = None,
    ema_ledger: Any | None = None,
    boltz: Any | None = None,
    molprops: Any | None = None,
) -> ToolRegistry:
    """Register only explicitly supplied adapter instances and return the registry."""

    if opentargets is not None:
        _register_opentargets(registry, opentargets)
    if chembl is not None:
        _register_chembl(registry, chembl)
    if pinned_evidence is not None:
        _register_pinned_evidence(registry, pinned_evidence)
    if clinical_synthesis is not None:
        _register_clinical_synthesis(registry, clinical_synthesis)
    if ctgov is not None:
        _register_ctgov(registry, ctgov)
    if ema is not None:
        _register_ema(registry, ema)
    if ema_ledger is not None:
        _register_ema_ledger(registry, ema_ledger)
    if boltz is not None:
        _register_boltz(registry, boltz)
    if molprops is not None:
        _register_molprops(registry, molprops)
    return registry
